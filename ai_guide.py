import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_repair_guide(bike_name, problem):
    prompt = f"""
You are a motorcycle mechanic assistant. Give a clear, practical repair guide for a rider who wants to fix their own bike.

Bike: {bike_name}
Problem: {problem}

Reply in this EXACT format, no extra text:

TITLE: (short title of the repair)
DIFFICULTY: (Easy / Moderate / Hard)
TIME: (estimated time)
INTERVAL: (how often this should be done, or N/A)
WARNING: (one important safety warning, or N/A)

TOOLS:
- tool 1
- tool 2

STEPS:
1. Step title | Step detail explanation
2. Step title | Step detail explanation
3. Step title | Step detail explanation

Keep steps practical and specific to the {bike_name}. Maximum 8 steps.
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_guide(response.choices[0].message.content)


def get_symptom_causes(bike_name, symptom):
    prompt = f"""
You are a motorcycle mechanic. A rider describes a problem with their bike.

Bike: {bike_name}
Problem: {symptom}

List the most likely causes. Reply in this EXACT format, no extra text:

CAUSES:
- cause | severity | can_diy
- cause | severity | can_diy

severity must be one of: high, medium, low
can_diy must be one of: yes, no

Maximum 5 causes, most likely first.
"""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return parse_causes(response.choices[0].message.content)


def parse_guide(text):
    guide = {
        "title": "",
        "difficulty": "",
        "time": "",
        "interval": "",
        "warning": "",
        "tools": [],
        "steps": []
    }

    lines = text.strip().split("\n")
    mode = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("TITLE:"):
            guide["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("DIFFICULTY:"):
            guide["difficulty"] = line.replace("DIFFICULTY:", "").strip()
        elif line.startswith("TIME:"):
            guide["time"] = line.replace("TIME:", "").strip()
        elif line.startswith("INTERVAL:"):
            guide["interval"] = line.replace("INTERVAL:", "").strip()
            if guide["interval"].lower() == "n/a":
                guide["interval"] = ""
        elif line.startswith("WARNING:"):
            guide["warning"] = line.replace("WARNING:", "").strip()
            if guide["warning"].lower() == "n/a":
                guide["warning"] = ""
        elif line.startswith("TOOLS:"):
            mode = "tools"
        elif line.startswith("STEPS:"):
            mode = "steps"
        elif mode == "tools" and line.startswith("-"):
            guide["tools"].append(line[1:].strip())
        elif mode == "steps" and line and line[0].isdigit():
            content = line.split(".", 1)[-1].strip()
            if "|" in content:
                title, detail = content.split("|", 1)
                guide["steps"].append({
                    "title": title.strip(),
                    "detail": detail.strip()
                })
            else:
                guide["steps"].append({
                    "title": content,
                    "detail": ""
                })

    return guide


def parse_causes(text):
    causes = []
    lines = text.strip().split("\n")
    mode = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("CAUSES:"):
            mode = "causes"
            continue
        if mode == "causes" and line.startswith("-"):
            parts = line[1:].strip().split("|")
            if len(parts) == 3:
                causes.append({
                    "issue":    parts[0].strip(),
                    "severity": parts[1].strip(),
                    "can_diy":  parts[2].strip()
                })

    return causes