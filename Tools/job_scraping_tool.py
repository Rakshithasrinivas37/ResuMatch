import re
import requests
import json
import uuid
from bs4 import BeautifulSoup
from pydantic import BaseModel
from jobspy import scrape_jobs
import pandas as pd

from crewai.tools import BaseTool

class JobSearchInput(BaseModel):
    role: str
    location: str
    min_experience: int
    max_experience: int

class JobSearchTool(BaseTool):
    name: str = "Job Search Tool"
    description: str = """Search and filter jobs by role, location
    and years of experience.
    Input: {\"role\": \"AI Engineer\", \"location\": \"Singapore\", \"min_experience\": \"0\", \"max_experience\": 3}"""
    args_schema: type[BaseModel] = JobSearchInput

    def extract_requirements(self, description):
    # Match everything between Requirements and Benefits/Why
        pattern = r'(?:Requirements|What are we looking for\?)(.*?)(?:Benefits|Why you|$)'
        match = re.search(pattern, description, re.DOTALL)

        if match:
            return match.group(1).strip()
        return description

    def extract_experience(self, description):
        if not description:
            return 0

        patterns = [
            r'(\d+)\s*[–\-—]\s*(\d+)\s*years?',             # 0–2 years, 3-5 years
            r'(\d+)\+?\s*years?\s*in\s*[\w\s]+',             # 6+ years in software engineering
            r'(\d+)\+?\s*years?\s*of\s*relevant\s*experience', # 5+ years of relevant experience
            r'(\d+)\+?\s*years?\s*of\s*experience',           # 5+ years of experience
            r'(\d+)\+?\s*years?\s*experience',                # 5+ years experience
            r'over\s*(\d+)\s*years?',                         # over 5 years
            r'minimum\s*(\d+)\s*years?',                      # minimum 5 years
            r'at\s*least\s*(\d+)\s*years?',                   # at least 3 years
            r'(\d+)\s*-\s*(\d+)\s*years?',                    # 3-5 years
        ]

        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return 0

    def clean_description(self, description):
        cleaned_description = description.replace("\n", "")
        cleaned_description = cleaned_description.replace("\\", "")

        # Remove multiple spaces
        cleaned_description = ' '.join(cleaned_description.split())


        return cleaned_description.strip()

    def scrape_foundit_jobs(self, role, location, min_experience=0, max_experience=3):
        url = "https://www.foundit.sg/middleware/jobSearch"

        params = {
            "query": role,
            "locations": location,
            "start": 0,
            "limit": 30
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.foundit.sg"
        }

        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        jobs = []

        # Extract job list
        job_list = data['jobSearchResponse']['data']

        for job in job_list:
            # Extract experience
            min_exp = job.get('minimumExperience', {}).get('years', 0)
            max_exp = job.get('maximumExperience', {}).get('years', 0)

            redirect_url = job.get('redirectUrl', '')
            if redirect_url.startswith('https://www.mycareersfuture.gov.sg/job/'):
                print(f"Skipping: {job.get('title')} — MyCareersFuture redirect")
                continue

            # Filter by experience range
            if min_exp == 0 or min_experience <= min_exp <= max_experience:
                if job.get('jobId') != None:
                    job_url = f"https://www.foundit.sg{job.get('jdUrl')}"

                    response = requests.get(job_url, headers=headers)

                    soup = BeautifulSoup(response.content, "html.parser")

                    # You must inspect the foundit.sg page to find the correct selector for the description
                    job_description_element = soup.find("div", class_="job-description-content") # Placeholder class name

                    if job_description_element:
                        job_description = job_description_element.get_text(strip=True, separator="\n")

                        jobs.append({
                            'id': str(job.get('jobId')),
                            'site': 'foundit',
                            'job_url': job_url,
                            'title': job.get('title'),
                            'company': job.get('companyName'),
                            'location': job.get('locations', location),
                            'date_posted': job.get('updatedAt'),
                            'job_type': job.get('employmentTypes', []),
                            'description': job_description,
                            'experience_required': int(min_exp) if min_exp else "Not specified"
                        })

        print(f"Total foundit jobs found: {len(jobs)}")
        return jobs

    def get_jobstreet_description(self, job_id, role="ai-engineer", location="Singapore"):
        url = "https://sg.jobstreet.com/graphql"

        session_id = "b2c39dd3-430b-4161-9ea4-bbac3fa804fd"
        correlation_id = str(uuid.uuid4())

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://sg.jobstreet.com",
            "Referer": f"https://sg.jobstreet.com/{role.lower().replace(' ','-')}-jobs/in-{location}?jobId={job_id}&type=standard",
            "seek-request-brand": "jobstreet",
            "seek-request-country": "SG",
            "X-Seek-Site": "chalice",
            "X-Seek-EC-SessionId": session_id,
            "X-Seek-EC-VisitorId": session_id
        }

        # Fresh cookies from your browser
        cookies = {
            "sol_id": "20eec8b1-4c48-4555-93b8-004fadd38208",
            "JobseekerSessionId": "d9eeb900-5993-4324-aac7-3059502773b7",
            "JobseekerVisitorId": "d9eeb900-5993-4324-aac7-3059502773b7",
            "__cf_bm": "tT_cJnW20ETdTJRNQzzMQbBTRaib5JwTIy1WaiM_mhU-1774078461-1.0.1.1-BGTqi1OsuuVK.1hVYEYgnYAvGfJG3eNzeHqoDDONZfEYSr_0aHU0cZAvaPP5miZDsgDQFItIA5MQUSPo6_3XyyEc0i3QhiHxQ78kSD1aP3k",
            "_cfuvid": "4TBO3xpmjJqcx0T0J9HV8gLJXIgr3pHdJBNQxOgqJpc-1774078461127-0.0.1.1-604800000",
            "_fbp": "fb.1.1773978394584.767765686111262117",
            "_ga": "GA1.1.1357352740.1773978394"
        }

        # Exact query from your browser
        payload = {
            "operationName": "jobDetails",
            "variables": {
                "jobId": str(job_id),
                "jobDetailsViewedCorrelationId": correlation_id,
                "sessionId": session_id,
                "zone": "asia-7",
                "locale": "en-SG",
                "timezone": "Asia/Singapore",
                "visitorId": "20eec8b1-4c48-4555-93b8-004fadd38208",
                "enableJdvBadge": True
            },
            "query": "query jobDetails($jobId: ID!, $jobDetailsViewedCorrelationId: String!, $sessionId: String!, $zone: Zone!, $locale: Locale!, $timezone: Timezone!, $visitorId: UUID!, $enableJdvBadge: Boolean!) {\n  jobDetails(\n    id: $jobId\n    tracking: {channel: \"WEB\", jobDetailsViewedCorrelationId: $jobDetailsViewedCorrelationId, sessionId: $sessionId}\n  ) {\n    ...job\n    learningInsights(platform: WEB, zone: $zone, locale: $locale) {\n      analytics\n      content\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment badges on JobDetails {\n  badges(visitorId: $visitorId, platform: WEB, locale: $locale) @include(if: $enableJdvBadge) {\n    badges {\n      badge\n      displayText(locale: $locale)\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment job on JobDetails {\n  job {\n    id\n    title\n    abstract\n    content(platform: WEB)\n    status\n    listedAt {\n      label(context: JOB_POSTED, length: SHORT, timezone: $timezone, locale: $locale)\n      dateTimeUtc\n      __typename\n    }\n    salary {\n      label\n      __typename\n    }\n    workTypes {\n      label(locale: $locale)\n      __typename\n    }\n    advertiser {\n      id\n      name(locale: $locale)\n      __typename\n    }\n    location {\n      label(locale: $locale, type: LONG)\n      __typename\n    }\n    products {\n      bullets\n      __typename\n    }\n    __typename\n  }\n  ...badges\n  __typename\n}"
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            cookies=cookies
        )

        if response.status_code != 200:
            print(response.text[:300])
            return "Not available"

        data = response.json()

        # Extract content
        job = data.get('data', {}) \
                .get('jobDetails', {}) \
                .get('job', {})

        if not job:
            print("No job found")
            print(json.dumps(data, indent=2)[:500])
            return "Not available"

        # Get HTML content and clean it
        content = job.get('content', '') or ''
        abstract = job.get('abstract', '') or ''

        if content:
            clean = BeautifulSoup(content, 'html.parser').get_text()
            clean = ' '.join(clean.split())
        else:
            clean = abstract

        return clean

    def scrape_jobstreet_jobs(self, role, location, min_experience=0, max_experience=3):

        url = "https://sg.jobstreet.com/graphql"

        # Copy these values from your browser Network tab
        # Network tab → /graphql request → Request Headers → Cookie
        cookies = {
            "sol_id": "20eec8b1-4c48-4555-93b8-004fadd38208",
            "JobseekerSessionId": "a12e38c7-92bc-421f-8b07-c11cadd2cd4f",
            "JobseekerVisitorId": "a12e38c7-92bc-421f-8b07-c11cadd2cd4f",
            "_fbp": "fb.1.1773978394584.767765686111262117",
            "__cf_bm": "uOIiY32QNw.aTXcysdw46UknLVuAqnKdx77fZoN561M-1773988196-1.0.1.1-oZZ5VBzhQWJiCucGSU7nANJkHKfU.Nbx4O7_6ElrJys2JM0xpgI4v6xbu2YApKFefv5lceZ7Sj8XcgpnbeLEGLMLUGXVkP5xp5Q7c7cYieg",
            "_cfuvid": "TOeCVoCh9p2.sLq3hkVk9NiJSf8sLPBDT5WBoE1_kJ0-1773988196184-0.0.1.1-604800000",
            "_ga": "GA1.1.1357352740.1773978394",
            "utag_main": "v_id:019d095a11ff0042b033c3f2c05c05075022a06d00b78"
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://sg.jobstreet.com",
            "Referer": f"https://sg.jobstreet.com/{role.lower().replace(' ', '-')}-jobs/in-{location}",
            "seek-request-brand": "jobstreet",
            "seek-request-country": "SG",
            "X-Seek-Site": "chalice",
            "x-custom-features": "application/features.seek.all+json",
            "X-Seek-EC-SessionId": "4e983143-00b4-46c0-99d7-3f40612c0e18",
            "X-Seek-EC-VisitorId": "4e983143-00b4-46c0-99d7-3f40612c0e18"
        }

        payload = {
            "operationName": "JobSearchV6",
            "variables": {
                "params": {
                    "channel": "web",
                    "eventCaptureSessionId": "4e983143-00b4-46c0-99d7-3f40612c0e18",
                    "eventCaptureUserId": "4e983143-00b4-46c0-99d7-3f40612c0e18",
                    "keywords": role,
                    "locale": "en-SG",
                    "page": 1,
                    "pageSize": 32,
                    "siteKey": "SG",
                    "source": "SEARCH_ENG",
                    "where": location,
                    "solId": "20eec8b1-4c48-4555-93b8-004fadd38208"
                },
                "locale": "en-SG",
                "timezone": "Asia/Singapore"
            },
            "query": """query JobSearchV6($params: JobSearchV6QueryInput!, $locale: Locale!, $timezone: Timezone!) {
                jobSearchV6(params: $params) {
                    data {
                        id
                        title
                        companyName
                        teaser
                        salaryLabel
                        workTypes
                        bulletPoints
                        roleId
                        listingDate {
                            label(context: JOB_POSTED, length: SHORT, timezone: $timezone, locale: $locale)
                        }
                        locations { label }
                        workArrangements { displayText }
                    }
                    totalCount
                }
            }"""
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            cookies=cookies
        )

        data = response.json()

        outer = data.get('data')
        if not outer:
            return []

        search_result = outer.get('jobSearchV6')
        if not search_result:
            return []

        job_list = search_result.get('data', [])

        jobs = []
        for job in job_list:
            locations = job.get('locations') or [{}]
            job_location = locations[0].get('label', location) if locations else location
            job_id = job.get('id')
            job_url = f"https://sg.jobstreet.com/{role.lower().replace(' ', '-')}-jobs/in-{location}?jobId={job_id}&type=standard"

            description = self.get_jobstreet_description(job_id)
            exp = self.extract_experience(description)

            if exp == 0 or min_experience <= exp <= max_experience:
                jobs.append({
                    'id': job.get('id'),
                    'title': job.get('title', ''),
                    'company': job.get('companyName') or 'Not specified',
                    'location': job_location,
                    'site': 'jobstreet',
                    'job_url': job_url,
                    'description': description,
                    'job_type': ', '.join(job.get('workTypes') or []),
                    'experience_required': exp if exp > 0 else "Not specified",
                    'date_posted': (job.get('listingDate') or {}).get('label', '')
                })

        print(f"Total jobstreet jobs: {len(jobs)}")
        return jobs

    def _run(self, role: str, location: str, min_experience: int, max_experience: int) -> str:
        all_jobs = []

        # Search each site separately
        sites = {
            'linkedin': {'linkedin_fetch_description': True},
            'indeed': {'country_indeed': 'singapore'},
        }

        for site_name, extra_params in sites.items():
          jobs = scrape_jobs(
              site_name=site_name,
              search_term=role,
              location=location,
              results_wanted=15,
              hours_old=72,
              **extra_params
          )

          for index, job in jobs.iterrows():
              cleaned_description = self.clean_description(job['description'])
              exp = self.extract_experience(cleaned_description)
              all_jobs.append(
                  {
                      "id": job['id'],
                      'site': job['site'],
                      'job_url': job['job_url'],
                      'title': job['title'],
                      'company': job['company'],
                      'location': job['location'],
                      'date_posted': job['date_posted'],
                      'job_type': job['job_type'],
                      'description': self.extract_requirements(cleaned_description),
                      'experience_required': exp if exp > 0 else "Not specified"
                  }
              )

        foundit_jobs = self.scrape_foundit_jobs(role, location, min_experience, max_experience)
        jobstreet_jobs = self.scrape_jobstreet_jobs(role, location, min_experience, max_experience)

        # Merge all jobs

        for job in foundit_jobs:
          all_jobs.append(job)

        for job in jobstreet_jobs:
          all_jobs.append(job)

        # Filter by experience range
        filtered_jobs = [
            job for job in all_jobs
            if job['experience_required'] == "Not specified"
            or (
                isinstance(job['experience_required'], int)
                and min_experience <= job['experience_required'] <= max_experience
            )
        ]

        return filtered_jobs