from crewai.agent import Agent
from crewai import Task

class JobMatcher:
    def __init__(self, llm):
        self.llm = llm

    def job_matcher_agent(self):
        self.agent = Agent(
            role="Job Match Analyzer",
            goal="""Analyze the match between a candidate's resume and job
                    requirements. Calculate a match score, identify skill gaps,
                    provide an upskilling roadmap and prepare interview tips.""",
            backstory="""You are a career coach and technical recruiter with
                        deep expertise in AI and software engineering roles.
                        You provide actionable insights to help candidates
                        land their dream jobs by identifying gaps and providing
                        clear guidance on how to bridge them.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=3,
            max_retry_limit=1
        )

        return self.agent
        
    def job_matcher_task(self, jobs, context=None, callback=None):
        ## Format all jobs into one prompt
        jobs_text = ""
        for i, job in enumerate(jobs):
            description_500_words = ' '.join(
                job.get('description', '').split()[:500]
            )
            jobs_text += f"""
            Job {i+1}:
            - Title:       {job['title']}
            - Company:     {job['company']}
            - Location:    {job['location']}
            - Job URL:     {job['job_url']}
            - Experience:  {job['experience_required']}
            - Description: {description_500_words}
            ---
            """

        total_jobs = len(jobs)

        job_matcher_task = Task(
            description=f"""You will receive parsed resume data from the previous
                task. Using that resume data and the following job details, perform
                a comprehensive job match analysis.

                ⚠️ THIS CHUNK CONTAINS EXACTLY {total_jobs} JOBS.
                YOU MUST ANALYZE AND RETURN ALL {total_jobs} JOBS.
                DO NOT STOP AFTER THE FIRST JOB.
                YOUR RESPONSE MUST BE A JSON LIST WITH EXACTLY {total_jobs} OBJECTS.

                Job Details:
                {jobs_text}

                ⚠️ STRICT RULES — YOU MUST FOLLOW THESE:
                - ONLY use information explicitly present in the resume
                - DO NOT invent, assume or generalize any skills or experience
                - EVERY claim must reference a specific project, skill or
                experience from the resume
                - If information is not in the resume, say "Not mentioned in resume"
                - DO NOT use phrases like "the candidate has experience with X"
                unless X is explicitly listed in the resume
                - Quote specific project names, metrics and technologies
                directly from the resume

                - ⚠️ PROCESS EVERY SINGLE JOB — Job 1 through Job {total_jobs}

                For EACH of the {total_jobs} jobs your analysis must include:

                Your analysis must include:

                1. MATCH SCORE (0-100):
                - Compare candidate skills vs required skills
                - Compare years of experience vs required experience
                - Compare education vs required education
                - Weight: Skills 50%, Experience 30%, Education 20%
                - Show the total score: x/100

                2. JOB MATCH ANALYSIS:
                IF match score > 75:
                - overall_summary: 2-3 sentences citing EXACT projects
                    and metrics from resume
                - matching_reasons: [reason + evidence from resume]

                IF match score <= 75:
                - what_matches:
                    * skills: [skill1, skill2, skill3, ...]  ← all in one line

                - what_doesnt_match:
                    * skills: [skill1, skill2, skill3, ...]  ← all in one line
                    * impact: High / Medium / Low

                - overall_assessment: 2 sentences on biggest gaps to address

                3. APPLICATION ELIGIBILITY DECISION:
                Based on match score and mandatory requirements decide:
                - verdict: STRONG APPLY / APPLY WITH CONFIDENCE /
                            APPLY WITH CAUTION / DO NOT APPLY YET
                - reason: 1-2 sentences using ONLY actual resume data
                - next_steps: 2 specific actions to improve candidacy

                4. SKILL GAP ANALYSIS:
                - List skills the candidate HAS that match the job
                - List skills REQUIRED by the job but MISSING from resume

        ⚠️ Keep ALL answers under 2 sentences — be concise!

                Don't hallucinate anything, clearly analyze the resume
                and job details and return the complete analysis as a
                structured JSON.
                """,
            expected_output="""A comprehensive JSON report with these
                fields at the TOP of the JSON:
                - job_title:   title of the job
                - company:     company name
                - job_url:     job URL
                - location: job location
                - match_score: score out of 100
                - score_breakdown
                - job_match_analysis
                - application_eligibility
                - skill_gap_analysis
                """,
            agent=self.agent,
            context=context or [],
            callback=callback or None
        )

        return job_matcher_task