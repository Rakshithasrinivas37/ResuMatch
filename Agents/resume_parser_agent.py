from crewai import Agent, Task
from Tools.resume_parser_tool import ResumeParserTool

class ResumeParser:
    def __init__(self, llm):
        self.llm = llm

    def resume_parser_agent(self):
        self.agent = Agent(
            llm=self.llm,
            role="Resume Parser",
            goal="Parse resume and extract relevant information.",
            backstory="""You are an expert resume parser who reads resumes
                        and extracts structured information accurately.
                        You identify technical skills, years of experience,
                        tools, frameworks and qualifications.""",
            tools=[ResumeParserTool],    # ✅ function reference
            verbose=True,
            allow_delegation=False,
            max_iter=3,                  # ✅ increased from 2
            max_retry_limit=1
        )
        return self.agent

    def resume_parser_task(self):
        return Task(
            description="""Use the resume_parser_tool to parse the resume file.

                Action: resume_parser_tool
                Action Input: {resume_path}

                ⚠️ IMPORTANT:
                - Pass {resume_path} as a plain string directly
                - DO NOT wrap in JSON or add any extra keys
                - DO NOT use {{"resume_path": "..."}} format

                The tool will return the full resume text.
                From that text extract and return:
                - current_role: most recent job title
                - total_experience_years: total years as a number
                - technical_skills: list of all technical skills
                - programming_languages: list of programming languages
                - tools: list of tools used
                - frameworks: list of frameworks used
                - education: list of {{degree, field, university, year}}
                - certifications: list of {{name, issuer}}
                - professional_experience: list of {{company, role, dates, projects}}

                Return ONLY structured JSON, no other text.
            """,
            expected_output="""JSON containing all extracted resume
                information including skills, experience and qualifications.""",
            agent=self.agent
        )