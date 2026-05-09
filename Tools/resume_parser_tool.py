from pdfminer.high_level import extract_text
from docx import Document
from docx.oxml.ns import qn
from crewai.tools import tool
from typing import Any
import json


def _extract_path(tool_input: Any) -> str:
    """Extract file path string from any format LLM sends."""
    if isinstance(tool_input, str):
        try:
            parsed = json.loads(tool_input)
            return _extract_path(parsed)
        except (json.JSONDecodeError, TypeError):
            return tool_input.strip()

    if isinstance(tool_input, dict):
        if "resume_path" in tool_input:
            val = tool_input["resume_path"]
            return val if isinstance(val, str) else str(val)
        if "properties" in tool_input:
            return _extract_path(tool_input["properties"])
        for val in tool_input.values():
            if isinstance(val, (dict, str)):
                result = _extract_path(val)
                if result:
                    return result
    return ""


def _extract_resume_text(resume_path: str) -> str:
    if resume_path.endswith('.pdf'):
        return extract_text(resume_path)

    doc = Document(resume_path)
    sections = {}
    current_section = "HEADER"

    def get_para_text(elem):
        return ''.join(t.text or '' for t in elem.iter(qn('w:t'))).strip()

    def is_heading(elem, text):
        style = elem.find('.//' + qn('w:pStyle'))
        style_val = style.get(qn('w:val'), '') if style is not None else ''
        return style_val.lower().startswith('heading') or text.isupper()

    def process_table(elem):
        rows = []
        for row in elem.iter(qn('w:tr')):
            cells = [
                ''.join(t.text or '' for t in cell.iter(qn('w:t'))).strip()
                for cell in row.iter(qn('w:tc'))
            ]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        return rows

    for elem in doc.element.body:
        tag = elem.tag.split('}')[-1]
        if tag == 'p':
            text = get_para_text(elem)
            if not text:
                continue
            if is_heading(elem, text):
                current_section = text
                sections.setdefault(current_section, [])
            else:
                sections.setdefault(current_section, []).append(text)
        elif tag == 'tbl':
            rows = process_table(elem)
            for cells in rows:
                if len(cells) == 2:
                    sections.setdefault(current_section, []).append(
                        f"{cells[0]} | {cells[1]}"
                    )
                else:
                    sections.setdefault(current_section, []).append(
                        ' '.join(cells)
                    )

    return '\n'.join(
        f'\n### {section} ###\n' + '\n'.join(lines)
        for section, lines in sections.items()
    )


@tool("resume_parser_tool")
def ResumeParserTool(resume_path: str) -> str:
    """Parses a resume PDF or DOCX file and extracts skills, experience
    and qualifications. Pass the file path as a plain string.
    Example: uploads/resumes/resume.pdf"""

    # ✅ Unwrap any nested input the LLM sends
    resume_path = _extract_path(resume_path)

    if not resume_path:
        return "Error: resume_path is required."

    print(f"Parsing resume at: {resume_path}")

    try:
        raw_text = _extract_resume_text(resume_path)
    except FileNotFoundError:
        return f"Error: File not found at path: {resume_path}"
    except Exception as e:
        return f"Error extracting resume: {str(e)}"

    # ✅ Return raw text directly — agent LLM will parse it
    return ' '.join(raw_text.split())