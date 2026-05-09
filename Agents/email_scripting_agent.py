from crewai import Agent, Task


class EmailScriptingAgent:
    def __init__(self, llm):
        self.llm = llm

    def email_scripting_agent(self):
        self.agent = Agent(
            role="Email Scripting Specialist",
            goal="""Create a compelling email subject and body to send
                    to the candidate with their job match results CSV
                    attached, highlighting interview tips for their
                    top matching jobs.""",
            backstory="""You are an expert career coach who sends
                        personalized job match reports to candidates.
                        You summarize their top job matches, highlight
                        key interview tips for each role, and motivate
                        them to take action. Your emails are warm,
                        encouraging and actionable.""",
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=2,
            max_retry_limit=1
        )
        return self.agent

    def email_scripting_task(self, jobs: list, candidate_name: str):
        """Create one email — subject + body — summarizing all job matches."""

        # ── Build job summary for prompt ───────────────
        jobs_summary = ""
        for i, job in enumerate(jobs):
            interview_questions = job.get("top_5_questions", "")
            if isinstance(interview_questions, list):
                interview_questions = " | ".join(interview_questions)

            jobs_summary += f"""
            Job {i+1}:
            - Title           : {job.get('job_title', 'N/A')}
            - Company         : {job.get('company', 'N/A')}
            - Match Score     : {job.get('match_score', 'N/A')}
            - Verdict         : {job.get('verdict', 'N/A')}
            - Matching Skills : {job.get('matching_skills', 'N/A')}
            - Missing Skills  : {job.get('missing_skills', 'N/A')}
            - Interview Tips  : {interview_questions}
            - Apply URL       : {job.get('job_url', 'N/A')}
            ---
            """

        total_jobs = len(jobs)
        top_job    = jobs[0] if jobs else {}

        return Task(
            description=f"""Create ONE email to send to the candidate
                {candidate_name} with their job match results.

                The CSV file with full match details will be
                attached separately — you only need to write
                the subject and body.

                Candidate: {candidate_name}
                Total jobs matched: {total_jobs}

                Job Match Summary:
                {jobs_summary}

                ⚠️ RULES:
                - Write ONE email — not one per job
                - Subject must mention interview tips
                - Body must be warm, encouraging and concise
                - Keep body under 300 words
                - Mention top 3 jobs by match score
                - Include 2-3 interview tips for the top matching job
                - Tell candidate the full details are in the attached CSV
                - End with an encouraging closing message

                EMAIL STRUCTURE:

                SUBJECT:
                - Must mention "Interview Tips" and candidate name
                - Reference the number of job matches
                - Example: "Your {total_jobs} Job Matches +
                  Interview Tips Inside, {candidate_name}!"

                BODY:
                1. Greeting: "Hi {candidate_name},"
                2. Opening: 1 sentence — their match results are ready
                3. Top matches: brief mention of top 3 jobs with scores
                4. Interview tips section: 2-3 tips for the top job
                   titled "💡 Quick Interview Tips for
                   [top job title] at [top company]:"
                5. CSV mention: tell them full details are in
                   the attached CSV file
                6. Closing: encouraging message to take action
                7. Sign off: "Best regards,\nResuMatch Team"

                Return ONLY a JSON object — no other text.
                """,
            expected_output="""A single JSON object:
                {
                    "subject": "email subject line mentioning interview tips",
                    "body"   : "full email body with greeting, job summary,
                                interview tips and CSV mention"
                }
                """,
            agent=self.agent
        )