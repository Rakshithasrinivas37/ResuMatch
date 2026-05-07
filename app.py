from pydantic import BaseModel
import pandas as pd
import os
import json

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Form
from fastapi.responses import FileResponse

from crewai.llm import LLM
from crewai import Crew, Process

from Tools.job_scraping_tool import JobSearchTool

app = FastAPI()

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