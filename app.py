from pydantic import BaseModel
import pandas as pd
import os
import json
import shutil
from pathlib import Path
import time
import re

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Form
from fastapi.responses import FileResponse

from crewai.llm import LLM
from crewai import Crew, Process

from Tools.job_scraping_tool import JobSearchTool
from Agents.resume_parser_agent import ResumeParser
from Agents.job_matcher_agent import JobMatcher

app = FastAPI()

# ── Define upload folder ───────────────────────────────
UPLOAD_DIR = Path("uploads/resumes")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)  # creates folder if not exists

class FetchJobsInput(BaseModel):
    role: str
    location: str
    min_exp: int
    max_exp: int

class AuthenticationDetils(BaseModel):
    mail_ID: str
    app_password: str

@app.post("/fetch_jobs")
def search_jobs(data: FetchJobsInput):
    job_search_tool = JobSearchTool()

    total_jobs = job_search_tool._run(data.role, data.location, data.min_exp, data.max_exp)

    print(type(total_jobs))

    # Save CSV here — not LLM's job
    df = pd.DataFrame(total_jobs)
    df.to_csv("job_results.csv", index=False)
    print(f"Saved {len(total_jobs)} jobs!")
    return {
        "message": f"Scraped {len(total_jobs)} job details for {data.role} in {data.location}"
    }

@app.get("/download_jobs")
def download_jobs():

    if not os.path.exists("job_results.csv"):
        raise HTTPException(status_code=404, detail="No job results found. Run /fetch_jobs first.")

    return FileResponse(
        path="job_results.csv",
        media_type="text/csv",
        filename="job_results.csv"
    )

# ── Helper: trim job fields ────────────────────────────
def trim_jobs(jobs: list) -> list:
    """Keep only fields relevant for matching — reduces tokens."""
    return [
        {
            "title"              : job.get("title", ""),
            "company"            : job.get("company", ""),
            "location"           : job.get("location", ""),
            "job_url"            : job.get("job_url", ""),
            "experience_required": job.get("experience_required", ""),
            # ✅ 500 words
            "description"        : " ".join(
                job.get("description", "").split()[:500]
            ),
        }
        for job in jobs
    ]

def chunk_jobs(jobs: list, chunk_size: int) -> list:
    """Split jobs list into chunks of chunk_size."""
    return [
        jobs[i:i + chunk_size]
        for i in range(0, len(jobs), chunk_size)
    ]

# ── Add delay between tasks ────────────────────────────
def after_task_callback(task_output):
    print(f"Task completed. Waiting 60s to respect TPM limit...")
    time.sleep(60)   # wait 60 seconds before next task

# ── Helper: parse JSON from text ───────────────────────
def extract_json_list(text: str) -> list:
    """Extract and combine all JSON arrays from text."""
    all_jobs = []
    json_blocks = re.findall(r'\[.*?\]', text, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, list):
                all_jobs.extend(parsed)
            elif isinstance(parsed, dict):
                all_jobs.append(parsed)
        except json.JSONDecodeError:
            continue

    # ── Deduplicate by job_url ─────────────────────────
    seen   = set()
    unique = []
    for job in all_jobs:
        url = job.get("job_url", "")
        if url not in seen:
            seen.add(url)
            unique.append(job)

    return unique



# ── Build crew ─────────────────────────────────────────
def build_crew(jobs: list, api_key: str, chunk_results: list) -> Crew:

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=api_key,
        temperature=0.0
    )

    # ✅ Collect results from each chunk via callback
    def collect_and_wait(task_output):
        try:
            raw   = str(task_output).strip()
            raw   = raw.removeprefix("```json").removesuffix("```").strip()
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    chunk_results.extend(parsed)
                    print(f"✅ Collected {len(parsed)} jobs. "
                          f"Total so far: {len(chunk_results)}")
                elif isinstance(parsed, dict):
                    chunk_results.append(parsed)
                    print(f"✅ Collected 1 job. "
                          f"Total so far: {len(chunk_results)}")
        except Exception as e:
            print(f"⚠️  Could not parse chunk result: {e}")

        print("Waiting 60s for Groq TPM limit...")
        time.sleep(60)

    trimmed_jobs = trim_jobs(jobs[:6])
    job_chunks   = chunk_jobs(trimmed_jobs, 3)

    # ── Resume parser ──────────────────────────────────
    resume_parser       = ResumeParser(llm)
    resume_parser_agent = resume_parser.resume_parser_agent()
    resume_parser_task  = resume_parser.resume_parser_task()

    # ── Job matcher ────────────────────────────────────
    job_matcher = JobMatcher(llm)
    job_matcher.job_matcher_agent()

    all_tasks     = [resume_parser_task]
    previous_task = resume_parser_task

    for i, chunk in enumerate(job_chunks):
        # ✅ Last chunk doesn't need delay
        cb = collect_and_wait if i < len(job_chunks) - 1 else (
            lambda task_output: _collect_only(task_output, chunk_results)
        )
        task = job_matcher.job_matcher_task(
            chunk,
            context=[previous_task],
            callback=cb
        )
        all_tasks.append(task)
        previous_task = task

    crew = Crew(
        agents=[resume_parser_agent, job_matcher.agent],
        tasks=all_tasks,
        process=Process.sequential,
        verbose=True,
        max_rpm=10
    )

    return crew

def _collect_only(task_output, chunk_results: list):
    """Collect last chunk result without delay."""
    try:
        raw   = str(task_output).strip()
        raw   = raw.removeprefix("```json").removesuffix("```").strip()
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                chunk_results.extend(parsed)
                print(f"✅ Final chunk collected {len(parsed)} jobs. "
                      f"Total: {len(chunk_results)}")
            elif isinstance(parsed, dict):
                chunk_results.append(parsed)
    except Exception as e:
        print(f"⚠️  Could not parse final chunk: {e}")

@app.post("/match_resume")
async def match_resume(
    resume: UploadFile = File(...),         # ✅ file passed separately
    job_results: str = Form(...),
    api_key: str = Form(...)
):
    # ── Save resume to folder ──────────────────────────
    file_path = UPLOAD_DIR / resume.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)

    print(f"Resume saved at: {file_path}")

    jobs = json.loads(job_results)

    # --------------- Build crew -------------------------
    chunk_results = []
    crew = build_crew(jobs, api_key, chunk_results)

    # --------------- Kickoff Crew -----------------------
    response = crew.kickoff(
            inputs={"resume_path": str(file_path)}
        )
    
    # ── Combine results from all chunks ────────────
    if chunk_results:
        match_results = chunk_results
        print(f"Combined {len(match_results)} jobs from chunks")
    else:
        match_results = extract_json_list(str(response))
        print(f"Parsed {len(match_results)} jobs from response")

    # ── Deduplicate by job_url ─────────────────────
    seen   = set()
    unique = []
    for job in match_results:
        url = job.get("job_url", "")
        if url not in seen:
            seen.add(url)
            unique.append(job)
    match_results = unique

    # ── Save results to CSV ────────────────────────
    if match_results:
        rows = []
        for job in match_results:
            # ✅ Flatten nested JSON into CSV columns
            score_breakdown   = job.get("score_breakdown", {})
            eligibility       = job.get("application_eligibility", {})
            skill_gap         = job.get("skill_gap_analysis", {})
            job_match         = job.get("job_match_analysis", {})

            rows.append({
                # ── Basic info ─────────────────────
                "job_title"         : job.get("job_title", ""),
                "company"           : job.get("company", ""),
                "location"          : job.get("location", ""),
                "job_url"           : job.get("job_url", ""),
                "match_score"       : job.get("match_score", 0),

                # ── Score breakdown ────────────────
                "skills_score"      : score_breakdown.get("skills_score", ""),
                "experience_score"  : score_breakdown.get("experience_score", ""),
                "education_score"   : score_breakdown.get("education_score", ""),

                # ── Eligibility ────────────────────
                "verdict"           : eligibility.get("verdict", ""),
                "reason"            : eligibility.get("reason", ""),
                "next_steps"        : " | ".join(eligibility.get("next_steps", [])),

                # ── Skill gap ──────────────────────
                "matching_skills"   : ", ".join(skill_gap.get("matching_skills", [])),
                "missing_skills"    : ", ".join(skill_gap.get("missing_skills", [])),
                "bonus_skills"      : ", ".join(skill_gap.get("bonus_skills", [])),

                # ── Overall assessment ─────────────
                "overall_assessment": (
                    job_match.get("overall_assessment") or
                    job_match.get("overall_summary", "")
                ),

                # ── Resume file ────────────────────
                "resume_file"       : resume.filename,
                "matched_at"        : pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            })

        results_df = pd.DataFrame(rows)

        # ✅ Append to existing CSV or create new one
        csv_path = "match_results.csv"
        if os.path.exists(csv_path):
            existing_df = pd.read_csv(csv_path)
            combined_df = pd.concat(
                [existing_df, results_df], ignore_index=True
            )
            # ✅ Deduplicate by job_url + resume_file
            combined_df = combined_df.drop_duplicates(
                subset=["job_url", "resume_file"], keep="last"
            )
            combined_df.to_csv(csv_path, index=False)
        else:
            results_df.to_csv(csv_path, index=False)

        print(f"Saved {len(rows)} match results to {csv_path}")

    return {
        "message": f"Saved {len(rows)} match results to {csv_path}"
    }

@app.get("/download_match_results")
def download_match_results():

    if not os.path.exists("match_results.csv"):
        raise HTTPException(status_code=404, detail="No match results found. Run /fetch_jobs first.")

    return FileResponse(
        path="match_results.csv",
        media_type="text/csv",
        filename="match_results.csv"
    )