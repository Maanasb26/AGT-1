from flask import Flask, render_template, request, jsonify
from urllib.parse import quote
import os
import re
import json
import smtplib
import ssl
import traceback
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape as html_escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024

# ============================================================
# CONFIGURATION
# ============================================================
TARGET_EMAILS = [x.strip() for x in os.getenv("TARGET_EMAIL", "maanasbrahme@gmail.com").split(",") if x.strip()]
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "918421957900")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        print(f"Invalid {name}; using {default}.")
        return default

SMTP_PORT = env_int("SMTP_PORT", 587)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "maanasbrahme@gmail.com").strip()
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "").strip()
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "tls").strip().lower()  # tls or ssl

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Gemini 3.5 Flash is a GA production model. 3.6 is kept as the first
# fallback because both are supported by the current Gemini API.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
GEMINI_FALLBACK_MODELS = [
    x.strip()
    for x in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash").split(",")
    if x.strip() and x.strip() != GEMINI_MODEL
]
GEMINI_TIMEOUT_SECONDS = env_int("GEMINI_TIMEOUT_SECONDS", 8)

# Render Free blocks outbound SMTP. We therefore support an HTTPS email API
# (Resend) as the production option while retaining Gmail SMTP locally / on
# paid Render. Set EMAIL_PROVIDER=resend and RESEND_API_KEY on Render Free.
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "").strip()
EMAIL_TIMEOUT_SECONDS = env_int("EMAIL_TIMEOUT_SECONDS", 8)

# No persistent SDK client is used for Gemini. Direct HTTPS requests give us
# an explicit socket timeout and prevent SDK-level retries from hanging a
# Gunicorn worker.
ai_client = bool(GEMINI_API_KEY)

# ============================================================
# AASPIREYA SERVICE PORTFOLIO
# ============================================================
ALL_SERVICES = [
    "German Customer Support (24/7 Voice & Chat)",
    "German Email & Ticket Handling",
    "AI-Powered Automated Chat Assistant",
    "Back-Office Data & Order Processing",
    "Dedicated Executive Virtual Assistance",
    "AI + Robotic Workflow Automation (RPA)",
    "Operational Analytics & KPI Dashboards",
    "Multilingual Enterprise Communication Support",
    "Omnichannel Customer Experience (CX) Management)",
    "Quality Assurance & Escalation Management",
]
# Correct the one service label while keeping the public portfolio explicit.
ALL_SERVICES[8] = "Omnichannel Customer Experience (CX) Management"

INDUSTRIES = [
    "E-Commerce & Retail Logistics",
    "SaaS & Cloud Software",
    "Fintech & Digital Banking",
    "Manufacturing & Industrial",
    "Travel & Hospitality",
    "Healthcare & Pharma",
    "Cross-Border B2B Services",
    "Other",
]

# ============================================================
# INPUT HELPERS
# ============================================================
def clean_text(value, max_length=5000):
    if value is None:
        return ""
    return str(value).strip()[:max_length]


def clean_email(value):
    value = clean_text(value, 320).lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        return None
    return value


def clean_list(value, max_items=ALL_SERVICES.__len__(), max_length=200):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:max_items]:
        item = clean_text(item, max_length)
        if item and item not in result:
            result.append(item)
    return result


def safe_int(value, default=0, minimum=None, maximum=None):
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        n = default
    if minimum is not None:
        n = max(minimum, n)
    if maximum is not None:
        n = min(maximum, n)
    return n


def normalise_score_dimensions(dimensions):
    names = [
        "Problem Severity",
        "Operational Complexity",
        "Aaspireya Service Fit",
        "Automation Potential",
        "Strategic / Growth Fit",
    ]
    if not isinstance(dimensions, list):
        dimensions = []
    by_name = {str(d.get("name", "")).strip().lower(): d for d in dimensions if isinstance(d, dict)}
    output = []
    for name in names:
        d = by_name.get(name.lower(), {})
        output.append({
            "name": name,
            "score": safe_int(d.get("score"), 0, 0, 20),
            "rationale": clean_text(d.get("rationale", ""), 280),
        })
    return output


def score_from_dimensions(dimensions):
    return max(0, min(100, sum(d["score"] for d in dimensions)))


def opportunity_level(score):
    if score >= 82:
        return "High Potential"
    if score >= 65:
        return "Good Potential"
    if score >= 45:
        return "Potential Identified"
    return "Early-Stage Opportunity"


def urgency_from_text(data):
    text = " ".join([
        data.get("query", ""),
        data.get("desired_outcome", ""),
        data.get("timeline", ""),
    ]).lower()
    if any(x in text for x in ["urgent", "immediately", "asap", "critical", "backlog", "overwhelmed"]):
        return "High"
    if any(x in text for x in ["soon", "1–3 months", "1-3 months", "30 days"]):
        return "Medium"
    return "Low"

# ============================================================
# FALLBACK ASSESSMENT
# ============================================================
def fallback_dimensions(data):
    text = json.dumps(data, ensure_ascii=False).lower()
    severity = 8 if any(x in text for x in ["critical", "urgent", "backlog", "overwhelmed", "lost customers", "complaints"]) else 6
    complexity = 8 if any(x in text for x in ["multiple", "omnichannel", "international", "manual", "erp", "crm", "volume"]) else 5
    fit = min(20, 8 + min(8, len(data.get("selected_services", [])) * 2))
    automation = 9 if any(x in text for x in ["automation", "manual", "repetitive", "workflow", "ai", "rpa"]) else 5
    strategic = 8 if any(x in text for x in ["growth", "scale", "scaling", "international", "customer", "efficiency"]) else 6
    return [
        {"name": "Problem Severity", "score": severity, "rationale": "Based on the stated operational pressure and business challenge."},
        {"name": "Operational Complexity", "score": complexity, "rationale": "Based on the number of processes, channels, teams or systems described."},
        {"name": "Aaspireya Service Fit", "score": fit, "rationale": "Based on alignment between the stated need and Aaspireya's service portfolio."},
        {"name": "Automation Potential", "score": automation, "rationale": "Based on evidence of repetitive, manual or workflow-driven work."},
        {"name": "Strategic / Growth Fit", "score": strategic, "rationale": "Based on the stated growth, CX, scalability or efficiency objective."},
    ]


def get_fallback_report(data):
    company = data.get("company", "your organisation")
    industry = data.get("product_type", "Business Operations")
    product = data.get("product", "your operations")
    query = data.get("query", "operational improvement")
    selected = data.get("selected_services", [])
    dimensions = fallback_dimensions(data)
    score = score_from_dimensions(dimensions)
    selected_valid = [s for s in selected if s in ALL_SERVICES]

    recommended = selected_valid[:4]
    if not recommended:
        recommended = [
            "AI + Robotic Workflow Automation (RPA)",
            "Operational Analytics & KPI Dashboards",
            "Quality Assurance & Escalation Management",
        ]

    service_objects = []
    for idx, service in enumerate(recommended):
        service_objects.append({
            "service": service,
            "match_score": max(70, 94 - idx * 5),
            "value_proposition": f"This capability is relevant to {company}'s stated challenge because it can address the operating need described around {product}.",
            "roi_impact": "Potential improvement in capacity, consistency, responsiveness or manual workload; quantify after workflow and volume discovery.",
        })

    return {
        "report_title": f"{company} Transformation Opportunity",
        "opportunity_score": score,
        "opportunity_level": opportunity_level(score),
        "industry_classification": f"{industry} / Business Operations",
        "urgency_rating": urgency_from_text(data),
        "decision_focus": "Validate the highest-impact workflow and establish a measurable pilot scope.",
        "diagnosis_rationale": f"The assessment is based on the business context supplied by {company}, including its operating model, selected improvement areas and stated challenge.",
        "executive_summary": f"{company} appears to have a practical transformation opportunity around {product}. The central issue described is: {query}. Aaspireya should approach this as a client-specific operating-model problem rather than applying a generic outsourcing package. The first priority is to isolate the workflows creating the greatest operational friction, then determine which activities should be automated, augmented by AI, or handled by trained specialists.\n\nThe strongest opportunity is to connect process design, customer or back-office execution, automation and measurement into one operating model. This can improve scalability and control while preserving human judgement for exceptions, sensitive interactions and escalations. The precise commercial impact should be validated using real volumes, handling times, quality data and process baselines during discovery.",
        "german_executive_summary": f"{company} zeigt auf Basis der bereitgestellten Informationen ein konkretes Potenzial zur Optimierung der operativen Abläufe. Die zentrale Herausforderung betrifft {product}: {query}. Aaspireya sollte hierfür kein standardisiertes Modell anwenden, sondern zunächst die relevanten Prozesse, Volumen, Engpässe und Qualitätsanforderungen analysieren.\n\nEin sinnvoller Ansatz ist die Kombination aus KI, Automatisierung und qualifizierter menschlicher Unterstützung. Wiederkehrende und regelbasierte Aufgaben können für Automatisierung geprüft werden, während komplexe Fälle, Eskalationen und kundenkritische Situationen durch Fachkräfte unterstützt werden. Der tatsächliche wirtschaftliche Effekt sollte anhand realer Prozessdaten im Rahmen einer Discovery validiert werden.",
        "primary_challenges": [
            f"The stated bottleneck is concentrated around: {query}",
            "Manual or fragmented work may limit speed, consistency or scalability.",
            "The current process baseline, volumes and quality metrics need validation before a business case is finalised.",
        ],
        "business_opportunities": [
            "Redesign the highest-friction workflow around clear ownership and measurable outcomes.",
            "Use AI and automation selectively for repetitive classification, routing, data handling and standard responses.",
            "Create a scalable human-support layer for exceptions, judgement, empathy and escalation.",
        ],
        "automation_opportunities": [
            "AI-assisted classification and prioritisation of inbound requests.",
            "Automated routing, data capture and CRM / ticket updates.",
            "Workflow triggers, exception alerts and operational KPI reporting.",
            "AI-assisted drafting of routine customer or operational responses with human review where appropriate.",
        ],
        "recommended_channels": ["Email", "Chat", "Voice", "Back-office workflow"],
        "recommended_services": service_objects,
        "selected_services": selected_valid,
        "score_dimensions": dimensions,
        "business_impact_areas": [
            {"area": "Capacity", "potential": "Create additional operating capacity by reducing avoidable manual work."},
            {"area": "Speed", "potential": "Improve response and processing speed through better routing and automation."},
            {"area": "Quality", "potential": "Increase consistency with QA controls, standard workflows and clearer escalation paths."},
            {"area": "Scalability", "potential": "Build a model that can handle higher volume without linear operational growth."},
        ],
        "solution_recommendation": "Start with a focused discovery of the highest-volume or highest-friction workflow. Map the current process, identify automation candidates, define the human-in-the-loop model, establish KPIs and then launch a controlled pilot before broader rollout.",
        "operational_diagram": "CLIENT / CUSTOMER / BUSINESS INPUT\n        |\n        v\nINTAKE → AI CLASSIFICATION → PRIORITY / ROUTING\n        |                    |\n        |                    +----> AUTOMATED ACTION\n        |\n        +------------------------> HUMAN EXPERT / ESCALATION\n                                  |\n                                  v\n                         RESOLUTION / PROCESS COMPLETION\n                                  |\n                                  v\n                         KPI + QA + CONTINUOUS IMPROVEMENT",
        "kpi_framework": [
            {"name": "First Response Time", "description": "Time from request receipt to first meaningful response."},
            {"name": "Resolution / Processing Time", "description": "Time required to complete the relevant customer or operational process."},
            {"name": "Automation Rate", "description": "Share of suitable workflow steps completed without manual intervention."},
            {"name": "Quality / QA Score", "description": "Accuracy and adherence to defined process and service standards."},
            {"name": "Backlog / Pending Work", "description": "Volume of unresolved or pending work over time."},
            {"name": "Customer Satisfaction", "description": "Customer perception of responsiveness and service quality where applicable."},
        ],
        "implementation_roadmap": [
            {"phase": "01 — Discovery & Baseline", "timeline": "Days 1–7", "details": "Map the current workflow, volumes, systems, roles, failure points, quality requirements and baseline KPIs."},
            {"phase": "02 — Solution Design", "timeline": "Days 8–15", "details": "Define the target operating model, automation candidates, human-in-the-loop controls, service scope and measurement plan."},
            {"phase": "03 — Pilot & Optimisation", "timeline": "Days 16–45+", "details": "Launch a controlled workflow pilot, monitor quality and operational KPIs, refine the process and prepare for scale."},
        ],
        "recommended_next_step": "Book a discovery session with Aaspireya to validate the highest-volume workflow, current baseline metrics, systems involved and the most practical pilot scope.",
        "cta_message": "The assessment is a decision-support starting point. A discovery session can turn the opportunity into a validated workflow, pilot scope and implementation plan.",
    }

# ============================================================
# GEMINI ENGINE
# ============================================================
def build_prompt(data):
    selected = data.get("selected_services", [])
    return f"""
You are the Senior Enterprise Solutions Architect and Business Transformation Consultant at Aaspireya Global Tech.

Your job is to produce a genuinely client-specific transformation assessment. Do not produce a generic BPO report. Every major recommendation must be traceable to the prospect's supplied business context.

AASPIREYA SERVICE PORTFOLIO — YOU MAY ONLY RECOMMEND SERVICES FROM THIS LIST:
{json.dumps(ALL_SERVICES, ensure_ascii=False, indent=2)}

Aaspireya capabilities include German-language customer support, AI-enabled customer experience, AI and workflow automation, back-office processing, virtual assistance, multilingual communication, omnichannel CX, analytics and QA. The operating philosophy is hybrid: automate/augment suitable repetitive work while skilled people handle judgement, empathy, exceptions and escalation.

PROSPECT PROFILE
Name: {data.get('name')}
Position: {data.get('position')}
Company: {data.get('company')}
Industry: {data.get('product_type')}
Product / Offering: {data.get('product')}
Selected improvement areas: {json.dumps(selected, ensure_ascii=False)}
Company size: {data.get('company_size') or 'Not provided'}
Primary market / geography: {data.get('geography') or 'Not provided'}
Approx. monthly customer / process volume: {data.get('monthly_volume') or 'Not provided'}
Current team handling this: {data.get('team_size') or 'Not provided'}
Current tools / channels: {data.get('current_tools') or 'Not provided'}
Current outsourcing / automation model: {data.get('current_model') or 'Not provided'}
Desired outcome: {data.get('desired_outcome') or 'Not provided'}
Desired timeline: {data.get('timeline') or 'Not provided'}
Business challenge: {data.get('query')}

ANALYSIS RULES
1. Be specific to this company, industry, offering, operating context and stated problem.
2. Treat selected improvement areas as client interests, not automatic recommendations. You must decide what is actually relevant.
3. Recommend only Aaspireya services from the exact portfolio above. Do not invent service names.
4. Explain why each recommended service fits this specific situation.
5. Identify the actual process or workflow that should be improved. Where the prospect did not provide enough detail, clearly say what must be validated.
6. Do not invent company facts, technology stacks, volumes, customer counts, logos, certifications, case studies or market facts.
7. Never claim guaranteed ROI, guaranteed savings or unsupported percentages.
8. Financial impact must be framed as a potential impact requiring validation.
9. Do not simply repeat the form fields. Synthesize them into a diagnosis.
10. Produce an AI-generated opportunity score. The score MUST equal the sum of the five dimension scores below. Each dimension is 0–20, total is 0–100.
11. Score dimensions based only on evidence in the supplied profile: Problem Severity, Operational Complexity, Aaspireya Service Fit, Automation Potential, Strategic / Growth Fit.
12. If information is missing, reduce confidence/score rather than inventing facts.
13. Keep the report commercially useful, credible and concise enough for a decision maker.
14. Return ONLY valid JSON. No markdown fences and no commentary outside JSON.

JSON STRUCTURE:
{{
  "report_title": "Specific title using the company or situation",
  "opportunity_score": 0,
  "opportunity_level": "High Potential | Good Potential | Potential Identified | Early-Stage Opportunity",
  "industry_classification": "Specific classification based on supplied information",
  "urgency_rating": "High | Medium | Low",
  "decision_focus": "The single most important decision or validation focus",
  "diagnosis_rationale": "2-4 sentences explaining why the assessment reached this conclusion",
  "executive_summary": "Two strong paragraphs written specifically for this prospect",
  "german_executive_summary": "Professional German version of the executive summary",
  "score_dimensions": [
    {{"name":"Problem Severity","score":0,"rationale":"Evidence-based reason"}},
    {{"name":"Operational Complexity","score":0,"rationale":"Evidence-based reason"}},
    {{"name":"Aaspireya Service Fit","score":0,"rationale":"Evidence-based reason"}},
    {{"name":"Automation Potential","score":0,"rationale":"Evidence-based reason"}},
    {{"name":"Strategic / Growth Fit","score":0,"rationale":"Evidence-based reason"}}
  ],
  "primary_challenges": ["3-5 highly specific challenges"],
  "business_opportunities": ["3-5 highly specific opportunities"],
  "business_impact_areas": [
    {{"area":"Capacity | Speed | Quality | Scalability | CX | Cost Control | Risk | Visibility","potential":"Specific potential impact without unsupported numeric claims"}}
  ],
  "solution_recommendation": "A detailed client-specific recommended operating approach",
  "automation_opportunities": ["3-6 concrete automation or AI opportunities tied to the stated workflow"],
  "recommended_channels": ["Only channels relevant to this client"],
  "recommended_services": [
    {{"service":"Exact service name from Aaspireya portfolio","match_score":0,"value_proposition":"Specific fit for this client","roi_impact":"Potential operational/commercial impact, with validation caveat"}}
  ],
  "operational_diagram": "Text workflow showing intake, AI/automation, human judgement and completion where relevant",
  "kpi_framework": [
    {{"name":"Specific KPI","description":"Why it matters for this client"}}
  ],
  "implementation_roadmap": [
    {{"phase":"01 — ...","timeline":"...","details":"Specific activity for this client"}},
    {{"phase":"02 — ...","timeline":"...","details":"Specific activity for this client"}},
    {{"phase":"03 — ...","timeline":"...","details":"Specific activity for this client"}}
  ],
  "recommended_next_step": "Specific next action for this prospect",
  "cta_message": "Short client-facing next-step message"
}}
"""


def sanitise_ai_report(result, data):
    if not isinstance(result, dict):
        raise ValueError("Gemini returned a non-object JSON response")

    dimensions = normalise_score_dimensions(result.get("score_dimensions"))
    score = score_from_dimensions(dimensions)
    result["score_dimensions"] = dimensions
    result["opportunity_score"] = score
    result["opportunity_level"] = opportunity_level(score)

    result["selected_services"] = [s for s in data.get("selected_services", []) if s in ALL_SERVICES]
    result["industry_classification"] = clean_text(result.get("industry_classification", data.get("product_type", "Business Operations")), 180)
    result["urgency_rating"] = clean_text(result.get("urgency_rating", "Medium"), 30)
    result["decision_focus"] = clean_text(result.get("decision_focus", "Validate the highest-impact workflow first."), 500)
    result["diagnosis_rationale"] = clean_text(result.get("diagnosis_rationale", ""), 1200)
    result["executive_summary"] = clean_text(result.get("executive_summary", ""), 5000)
    result["german_executive_summary"] = clean_text(result.get("german_executive_summary", ""), 5000)
    result["solution_recommendation"] = clean_text(result.get("solution_recommendation", ""), 4000)
    result["operational_diagram"] = clean_text(result.get("operational_diagram", ""), 3000)
    result["recommended_next_step"] = clean_text(result.get("recommended_next_step", ""), 1500)
    result["cta_message"] = clean_text(result.get("cta_message", ""), 1000)
    result["report_title"] = clean_text(result.get("report_title", f"{data.get('company', 'Client')} Transformation Opportunity"), 180)

    for key in ["primary_challenges", "business_opportunities", "automation_opportunities", "recommended_channels"]:
        raw_items = result.get(key)
        if not isinstance(raw_items, list):
            raw_items = []
        result[key] = [
            clean_text(x, 700)
            for x in raw_items
            if clean_text(x, 700)
        ]

    impacts = []
    for item in result.get("business_impact_areas") or []:
        if isinstance(item, dict):
            impacts.append({
                "area": clean_text(item.get("area", "Impact"), 100),
                "potential": clean_text(item.get("potential", "Validate during discovery."), 700),
            })
    result["business_impact_areas"] = impacts[:8]

    valid_services = []
    for item in result.get("recommended_services") or []:
        if not isinstance(item, dict):
            continue
        service = clean_text(item.get("service", ""), 180)
        if service not in ALL_SERVICES:
            continue
        valid_services.append({
            "service": service,
            "match_score": safe_int(item.get("match_score"), 75, 0, 100),
            "value_proposition": clean_text(item.get("value_proposition", ""), 1200),
            "roi_impact": clean_text(item.get("roi_impact", "Potential impact should be validated during discovery."), 1000),
        })
    result["recommended_services"] = valid_services[:7]

    kpis = []
    for item in result.get("kpi_framework") or []:
        if isinstance(item, dict):
            kpis.append({
                "name": clean_text(item.get("name", "KPI"), 100),
                "description": clean_text(item.get("description", ""), 500),
            })
    result["kpi_framework"] = kpis[:8]

    roadmap = []
    for item in result.get("implementation_roadmap") or []:
        if isinstance(item, dict):
            roadmap.append({
                "phase": clean_text(item.get("phase", "Implementation"), 120),
                "timeline": clean_text(item.get("timeline", "To be confirmed"), 80),
                "details": clean_text(item.get("details", ""), 1000),
            })
    result["implementation_roadmap"] = roadmap[:5]

    if not result["recommended_services"]:
        result["recommended_services"] = []
    if not result["kpi_framework"]:
        result["kpi_framework"] = [{"name": "Baseline KPI", "description": "Establish the current baseline during discovery."}]
    if not result["implementation_roadmap"]:
        result["implementation_roadmap"] = get_fallback_report(data)["implementation_roadmap"]

    return result


def _extract_gemini_text(payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    text = "\n".join(texts).strip()
    if not text:
        raise ValueError("Gemini returned an empty response.")
    return text


def _parse_json_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _call_gemini_rest(model, prompt):
    """One Gemini REST call with a hard socket timeout and zero SDK retries."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + quote(model, safe="")
        + ":generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    return _parse_json_response(_extract_gemini_text(payload))


def generate_comprehensive_assessment(data):
    """Generate AI output without ever allowing Gemini to hang the web worker.

    The primary model gets one bounded request. A second supported model is
    attempted only after a primary failure. If both fail, the deterministic
    report is returned so the client experience and email pipeline still work.
    """
    if not GEMINI_API_KEY:
        fallback = get_fallback_report(data)
        fallback["ai_status"] = "fallback_no_gemini"
        return fallback

    prompt = build_prompt(data)
    models = [GEMINI_MODEL] + GEMINI_FALLBACK_MODELS
    last_error = "Unknown Gemini error"

    for index, model in enumerate(models[:2], start=1):
        try:
            result = _call_gemini_rest(model, prompt)
            result = sanitise_ai_report(result, data)
            result["ai_status"] = "gemini_generated"
            result["ai_model"] = model
            return result
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:700]
            except Exception:
                detail = str(exc)
            last_error = f"{model}: HTTP {exc.code} — {detail}"
            print(f"Gemini model {model} failed: {last_error}")
        except Exception as exc:
            last_error = f"{model}: {clean_text(str(exc), 700)}"
            print(f"Gemini model {model} failed: {last_error}")

    fallback = get_fallback_report(data)
    fallback["ai_status"] = "fallback_after_gemini_error"
    fallback["ai_error"] = last_error
    return fallback


# ============================================================
# EMAIL RENDERING
# ============================================================
def render_bullets(items):
    return "".join(f"<li>{html_escape(str(x))}</li>" for x in items or [])


def render_email_html(data, report, client_copy=False):
    score = safe_int(report.get("opportunity_score"), 0, 0, 100)
    dims = report.get("score_dimensions", [])
    services = report.get("recommended_services", [])
    roadmap = report.get("implementation_roadmap", [])
    impacts = report.get("business_impact_areas", [])
    kpis = report.get("kpi_framework", [])

    dimension_rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #e8edf3;'>{html_escape(d.get('name',''))}</td><td style='padding:8px;border-bottom:1px solid #e8edf3;font-weight:800;'>{safe_int(d.get('score'),0,0,20)}/20</td><td style='padding:8px;border-bottom:1px solid #e8edf3;color:#5c6b7e;'>{html_escape(d.get('rationale',''))}</td></tr>"
        for d in dims
    )
    service_cards = "".join(
        f"<div style='padding:16px;margin:10px 0;border:1px solid #dfe8f2;border-left:4px solid #1769d2;border-radius:10px;background:#fbfdff;'><strong>{html_escape(s.get('service',''))}</strong><span style='float:right;background:#e9f8f3;color:#087654;padding:4px 8px;border-radius:20px;font-size:12px;font-weight:800;'>{safe_int(s.get('match_score'),0,0,100)}% match</span><p style='color:#5c6b7e;margin:9px 0;'>{html_escape(s.get('value_proposition',''))}</p><div style='color:#174b91;font-size:13px;font-weight:700;'>Potential impact: {html_escape(s.get('roi_impact',''))}</div></div>"
        for s in services
    )
    roadmap_html = "".join(
        f"<div style='padding:14px;border:1px solid #e1e8f1;border-radius:10px;margin:8px 0;'><strong>{html_escape(r.get('phase',''))}</strong><div style='color:#087654;font-weight:800;font-size:12px;margin-top:3px;'>{html_escape(r.get('timeline',''))}</div><p style='margin:6px 0;color:#5c6b7e;'>{html_escape(r.get('details',''))}</p></div>"
        for r in roadmap
    )
    impact_html = "".join(
        f"<li><strong>{html_escape(i.get('area',''))}:</strong> {html_escape(i.get('potential',''))}</li>"
        for i in impacts
    )
    kpi_html = "".join(
        f"<li><strong>{html_escape(k.get('name',''))}:</strong> {html_escape(k.get('description',''))}</li>"
        for k in kpis
    )

    recipient_name = html_escape(data.get("name", "there"))
    intro = (
        f"Here is the personalised Aaspireya transformation assessment prepared for {html_escape(data.get('company','your organisation'))}."
        if client_copy else
        "A new business transformation assessment has been submitted through the Aaspireya website."
    )

    return f"""<!doctype html><html><body style='margin:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#10233f;'>
<div style='max-width:820px;margin:0 auto;padding:28px 14px;'>
<div style='background:#071b49;color:white;border-radius:18px 18px 0 0;padding:28px;'>
<div style='font-size:11px;letter-spacing:1.4px;text-transform:uppercase;color:#9fe5cf;font-weight:800;'>Aaspireya Global Tech</div>
<h1 style='margin:8px 0 5px;font-size:28px;'>{html_escape(report.get('report_title','Business Transformation Assessment'))}</h1>
<p style='margin:0;color:#cbd7ea;'>{html_escape(report.get('opportunity_level','Potential Identified'))} · {html_escape(report.get('industry_classification','Business Operations'))}</p>
<div style='margin-top:22px;display:inline-block;background:white;color:#071b49;border-radius:14px;padding:13px 18px;'><span style='font-size:28px;font-weight:900;'>{score}</span><span style='font-size:11px;color:#5c6b7e;'> / 100 AI opportunity score</span></div>
</div>
<div style='background:white;border:1px solid #e1e8f1;border-top:0;padding:28px;border-radius:0 0 18px 18px;box-shadow:0 15px 45px rgba(7,27,73,.08);'>
<p style='color:#5c6b7e;'>{intro}</p>
{f"<p><strong>Hi {recipient_name},</strong></p>" if client_copy else ""}
{"" if client_copy else f"<h2 style='color:#071b49;'>Submitted Client Details</h2><table style='width:100%;border-collapse:collapse;font-size:14px;background:#fbfdff;border:1px solid #e1e8f1;border-radius:12px;overflow:hidden;'>" + "".join([f"<tr><td style='padding:9px;border-bottom:1px solid #e8edf3;font-weight:800;width:34%;'>{html_escape(label)}</td><td style='padding:9px;border-bottom:1px solid #e8edf3;color:#52647b;white-space:pre-line;'>{html_escape(value or 'Not provided')}</td></tr>" for label,value in [("Name",data.get("name")),("Position / Title",data.get("position")),("Business Email",data.get("email")),("Phone / WhatsApp",data.get("phone")),("Company",data.get("company")),("Industry",data.get("product_type")),("Product / Offering",data.get("product")),("Company Size",data.get("company_size")),("Geography",data.get("geography")),("Monthly Volume",data.get("monthly_volume")),("Current Team Size",data.get("team_size")),("Current Tools / Channels",data.get("current_tools")),("Current Outsourcing / Automation Model",data.get("current_model")),("Desired Outcome",data.get("desired_outcome")),("Desired Timeline",data.get("timeline")),("Selected Improvement Areas",", ".join(data.get("selected_services",[]))), ("Detailed Business Challenge",data.get("query"))]]) + "</table>"}
<h2 style='color:#071b49;'>Executive Diagnosis</h2>
<div style='padding:18px;background:#f7faff;border:1px solid #e5edf6;border-radius:12px;white-space:pre-line;color:#40536b;'>{html_escape(report.get('executive_summary',''))}</div>
<h2 style='color:#071b49;'>AI Opportunity Score</h2>
<table style='width:100%;border-collapse:collapse;font-size:13px;'><thead><tr><th align='left' style='padding:8px;border-bottom:2px solid #dce6f2;'>Dimension</th><th align='left' style='padding:8px;border-bottom:2px solid #dce6f2;'>Score</th><th align='left' style='padding:8px;border-bottom:2px solid #dce6f2;'>Reason</th></tr></thead><tbody>{dimension_rows}</tbody></table>
<h2 style='color:#071b49;'>Key Challenges</h2><ul style='line-height:1.7;color:#52647b;'>{render_bullets(report.get('primary_challenges',[]))}</ul>
<h2 style='color:#071b49;'>Transformation Opportunities</h2><ul style='line-height:1.7;color:#52647b;'>{render_bullets(report.get('business_opportunities',[]))}</ul>
<h2 style='color:#071b49;'>Recommended Aaspireya Services</h2>{service_cards}
<h2 style='color:#071b49;'>AI & Automation Opportunities</h2><ul style='line-height:1.7;color:#52647b;'>{render_bullets(report.get('automation_opportunities',[]))}</ul>
<h2 style='color:#071b49;'>Business Impact Areas</h2><ul style='line-height:1.7;color:#52647b;'>{impact_html}</ul>
<h2 style='color:#071b49;'>Recommended Solution</h2><div style='padding:18px;background:#f7faff;border:1px solid #e5edf6;border-radius:12px;color:#40536b;'>{html_escape(report.get('solution_recommendation',''))}</div>
<h2 style='color:#071b49;'>Implementation Roadmap</h2>{roadmap_html}
<h2 style='color:#071b49;'>KPI Framework</h2><ul style='line-height:1.7;color:#52647b;'>{kpi_html}</ul>
<h2 style='color:#071b49;'>Recommended Next Step</h2><div style='padding:18px;background:#eaf8f4;border:1px solid #cfece2;border-radius:12px;color:#244f46;font-weight:700;'>{html_escape(report.get('recommended_next_step',''))}</div>
<p style='margin-top:28px;font-size:12px;color:#7a8798;'>This assessment is a discovery tool. Any business impact, cost or ROI should be validated against the prospect's actual workflows, volumes, quality data and commercial requirements.</p>
</div></div></body></html>"""


def render_email_text(data, report, client_copy=False):
    lines = [
        "AASPIREYA GLOBAL TECH",
        "BUSINESS TRANSFORMATION ASSESSMENT",
        "=" * 70,
    ]
    if not client_copy:
        lines += [
            "SUBMITTED CLIENT DETAILS",
            f"Name: {data.get('name','')}",
            f"Position / Title: {data.get('position','')}",
            f"Business Email: {data.get('email','')}",
            f"Phone / WhatsApp: {data.get('phone') or 'Not provided'}",
            f"Company: {data.get('company','')}",
            f"Industry: {data.get('product_type','')}",
            f"Product / Offering: {data.get('product','')}",
            f"Company Size: {data.get('company_size') or 'Not provided'}",
            f"Geography: {data.get('geography') or 'Not provided'}",
            f"Monthly Volume: {data.get('monthly_volume') or 'Not provided'}",
            f"Current Team Size: {data.get('team_size') or 'Not provided'}",
            f"Current Tools / Channels: {data.get('current_tools') or 'Not provided'}",
            f"Current Outsourcing / Automation Model: {data.get('current_model') or 'Not provided'}",
            f"Desired Outcome: {data.get('desired_outcome') or 'Not provided'}",
            f"Desired Timeline: {data.get('timeline') or 'Not provided'}",
            f"Selected Improvement Areas: {', '.join(data.get('selected_services', [])) or 'Not provided'}",
            "Detailed Business Challenge:",
            data.get('query',''),
            "",
        ]
    lines += [
        f"Company: {data.get('company','')}",
        f"Industry: {data.get('product_type','')}",
        f"AI Opportunity Score: {report.get('opportunity_score',0)}/100",
        f"Opportunity Level: {report.get('opportunity_level','')}",
        "",
        "EXECUTIVE DIAGNOSIS",
        report.get("executive_summary", ""),
        "",
        "SCORE DIMENSIONS",
    ]
    for d in report.get("score_dimensions", []):
        lines.append(f"- {d.get('name')}: {d.get('score')}/20 — {d.get('rationale')}")
    lines += ["", "KEY CHALLENGES"]
    lines += [f"- {x}" for x in report.get("primary_challenges", [])]
    lines += ["", "TRANSFORMATION OPPORTUNITIES"]
    lines += [f"- {x}" for x in report.get("business_opportunities", [])]
    lines += ["", "RECOMMENDED SERVICES"]
    for s in report.get("recommended_services", []):
        lines += [f"- {s.get('service')} ({s.get('match_score')}% match)", f"  Fit: {s.get('value_proposition')}", f"  Impact: {s.get('roi_impact')}"]
    lines += ["", "AI & AUTOMATION OPPORTUNITIES"]
    lines += [f"- {x}" for x in report.get("automation_opportunities", [])]
    lines += ["", "IMPLEMENTATION ROADMAP"]
    for r in report.get("implementation_roadmap", []):
        lines.append(f"- {r.get('phase')} | {r.get('timeline')} | {r.get('details')}")
    lines += ["", "RECOMMENDED NEXT STEP", report.get("recommended_next_step", ""), "", "Generated by the Aaspireya Global Tech transformation assessment engine."]
    return "\n".join(lines)


def _send_email_smtp(to_addresses, subject, html_body, text_body, reply_to=None):
    if not SENDER_PASSWORD:
        raise RuntimeError("SENDER_PASSWORD is missing. For Gmail, use a Gmail App Password.")
    if not SENDER_EMAIL:
        raise RuntimeError("SENDER_EMAIL is missing.")
    if not to_addresses:
        raise RuntimeError("No recipient email configured.")

    msg = MIMEMultipart("alternative")
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(to_addresses)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    if SMTP_SECURITY == "ssl" or SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=EMAIL_TIMEOUT_SECONDS) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_addresses, msg.as_string())
    else:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=EMAIL_TIMEOUT_SECONDS) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_addresses, msg.as_string())


def _send_email_resend(to_addresses, subject, html_body, text_body, reply_to=None):
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is missing.")
    if not RESEND_FROM:
        raise RuntimeError("RESEND_FROM is missing. Use a verified sender/domain in Resend.")
    if not to_addresses:
        raise RuntimeError("No recipient email configured.")

    payload = {
        "from": RESEND_FROM,
        "to": list(to_addresses),
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=EMAIL_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8", errors="replace")
    result = json.loads(raw or "{}")
    if not result.get("id"):
        raise RuntimeError(f"Email API returned no message id: {raw[:500]}")
    return result["id"]


def send_one_email(to_addresses, subject, html_body, text_body, reply_to=None):
    """Send via the selected provider with a hard timeout."""
    if EMAIL_PROVIDER == "resend":
        return _send_email_resend(to_addresses, subject, html_body, text_body, reply_to)
    return _send_email_smtp(to_addresses, subject, html_body, text_body, reply_to)


def send_assessment_emails(data, report):
    """Send the internal lead email and client email in parallel.

    Unlike the previous daemon-thread approach, this returns only after the
    provider has accepted both messages or reported an error. That makes the
    HTTP response truthful about email delivery/acceptance.
    """
    if not SENDER_EMAIL and EMAIL_PROVIDER == "smtp":
        return False, False, ["SENDER_EMAIL is missing."]
    if EMAIL_PROVIDER == "smtp" and not SENDER_PASSWORD:
        return False, False, ["SENDER_PASSWORD is missing. Use a Gmail App Password."]
    if EMAIL_PROVIDER == "resend" and (not RESEND_API_KEY or not RESEND_FROM):
        return False, False, ["Resend is not configured. Set RESEND_API_KEY and RESEND_FROM."]
    if not TARGET_EMAILS:
        return False, False, ["TARGET_EMAIL is missing."]

    internal_html = render_email_html(data, report, client_copy=False)
    internal_text = render_email_text(data, report, client_copy=False)
    client_html = render_email_html(data, report, client_copy=True)
    client_text = render_email_text(data, report, client_copy=True)

    jobs = [
        ("internal", TARGET_EMAILS,
         f"🚀 New Aaspireya Business Opportunity — {data.get('company', 'New Lead')}",
         internal_html, internal_text, data.get("email")),
    ]
    if data.get("email"):
        jobs.append(("client", [data["email"]],
                     "Your Aaspireya Business Transformation Assessment",
                     client_html, client_text, SENDER_EMAIL))

    sent_internal = False
    sent_client = False
    errors = []

    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="aaspireya-email") as pool:
        future_map = {
            pool.submit(send_one_email, recipients, subject, html, text, reply_to): kind
            for kind, recipients, subject, html, text, reply_to in jobs
        }
        for future in as_completed(future_map):
            kind = future_map[future]
            try:
                message_id = future.result()
                print(f"{kind.upper()} EMAIL ACCEPTED:", message_id)
                if kind == "internal":
                    sent_internal = True
                else:
                    sent_client = True
            except Exception as exc:
                message = f"{kind.title()} email: {clean_text(str(exc), 600)}"
                errors.append(message)
                print("EMAIL FAILURE:", message)

    return sent_internal, sent_client, errors


# ============================================================
# WHATSAPP
# ============================================================
def create_whatsapp_url(data, report):
    number = re.sub(r"[^0-9]", "", WHATSAPP_NUMBER)
    message = (
        "Hello Aaspireya Global Tech,\n\n"
        "I have completed the Business Transformation Assessment.\n\n"
        f"Company: {data.get('company')}\n"
        f"Industry: {data.get('product_type')}\n"
        f"AI Opportunity Score: {report.get('opportunity_score','N/A')}/100\n\n"
        "I would like to discuss the recommended solution with your team."
    )
    return f"https://wa.me/{number}?text={quote(message)}"

# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def home():
    return render_template("index.html", industries=INDUSTRIES)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "gemini_configured": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "gemini_fallback_models": GEMINI_FALLBACK_MODELS,
        "gemini_timeout_seconds": GEMINI_TIMEOUT_SECONDS,
        "email_provider": EMAIL_PROVIDER,
        "email_configured": bool((EMAIL_PROVIDER == "resend" and RESEND_API_KEY and RESEND_FROM and TARGET_EMAILS) or (EMAIL_PROVIDER == "smtp" and SENDER_PASSWORD and SENDER_EMAIL and TARGET_EMAILS)),
        "target_email_count": len(TARGET_EMAILS),
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        # Always parse JSON silently so malformed/non-JSON requests become
        # a controlled JSON error instead of Flask's default HTML error page.
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "message": "Invalid or missing JSON request body."
            }), 400

        required = ["name", "position", "email", "company", "product_type", "product", "query"]
        for field in required:
            if not clean_text(data.get(field)):
                return jsonify({
                    "success": False,
                    "message": f"Please complete {field.replace('_', ' ')}."
                }), 400

        # Normalise every incoming field before any downstream processing.
        data["name"] = clean_text(data.get("name"), 120)
        data["position"] = clean_text(data.get("position"), 160)
        data["company"] = clean_text(data.get("company"), 180)
        data["product_type"] = clean_text(data.get("product_type"), 150)
        data["product"] = clean_text(data.get("product"), 1000)
        data["query"] = clean_text(data.get("query"), 5000)
        data["phone"] = clean_text(data.get("phone"), 60)
        data["company_size"] = clean_text(data.get("company_size"), 100)
        data["geography"] = clean_text(data.get("geography"), 180)
        data["monthly_volume"] = clean_text(data.get("monthly_volume"), 180)
        data["team_size"] = clean_text(data.get("team_size"), 180)
        data["current_tools"] = clean_text(data.get("current_tools"), 500)
        data["current_model"] = clean_text(data.get("current_model"), 180)
        data["desired_outcome"] = clean_text(data.get("desired_outcome"), 700)
        data["timeline"] = clean_text(data.get("timeline"), 120)

        email = clean_email(data.get("email"))
        if not email:
            return jsonify({
                "success": False,
                "message": "Please enter a valid business email address."
            }), 400
        data["email"] = email

        selected = clean_list(
            data.get("selected_services"),
            max_items=len(ALL_SERVICES),
            max_length=180
        )
        data["selected_services"] = [
            x for x in selected if x in ALL_SERVICES
        ]
        if not data["selected_services"]:
            return jsonify({
                "success": False,
                "message": "Please select at least one improvement area."
            }), 400

        report = generate_comprehensive_assessment(data)

        # Email failure must never destroy an otherwise successful assessment.
        internal_sent, client_sent, email_errors = send_assessment_emails(data, report)
        whatsapp_url = create_whatsapp_url(data, report)

        response_payload = {
            "success": True,
            "message": "Your Aaspireya Business Transformation Assessment has been generated.",
            "email_sent": bool(internal_sent),
            "client_email_sent": bool(client_sent),
            "email_errors": list(email_errors or []),
            "assessment": report,
            "whatsapp_url": whatsapp_url,
        }

        # Force a serialization check before sending the response.
        # This guarantees the browser receives valid JSON or a controlled
        # server error, never a Python object/HTML response.
        json.dumps(response_payload, ensure_ascii=False, allow_nan=False)

        return jsonify(response_payload), 200

    except Exception as error:
        print("ROUTE ERROR:", error)
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "We could not complete the assessment. Please try again.",
        }), 500


# JSON error handlers for API routes. These prevent Flask/Render's default
# HTML error pages from reaching fetch() and causing "Unexpected token '<'".
@app.errorhandler(400)
def handle_bad_request(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "message": "Bad request. Please check the submitted assessment data."
        }), 400
    return error


@app.errorhandler(404)
def handle_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "message": "API endpoint not found."
        }), 404
    return error


@app.errorhandler(405)
def handle_method_not_allowed(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "message": "This API endpoint does not support that HTTP method."
        }), 405
    return error


@app.errorhandler(413)
def handle_payload_too_large(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "message": "The submitted assessment is too large."
        }), 413
    return error


@app.errorhandler(500)
def handle_internal_error(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "message": "The server encountered an internal error. Check the Render logs."
        }), 500
    return error


if __name__ == "__main__":
    port = env_int("PORT", 5003)
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=port, debug=debug)