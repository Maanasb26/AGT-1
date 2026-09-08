# Aaspireya Global Tech — AI Business Transformation Assessment

An AI-powered business transformation assessment platform built for **Aaspireya Global Tech**.

The platform collects structured information about a prospective client's organisation, business operations and current challenges, analyses the information using a Gemini large language model, generates a personalised transformation assessment, calculates an AI opportunity score, recommends relevant Aaspireya services, identifies automation opportunities and provides an implementation roadmap.

The application is designed as a practical **AI-enabled business decision-support and lead-generation platform**, combining a responsive web interface, Flask backend, LLM integration, deterministic fallback logic, automated email delivery and WhatsApp lead conversion.

---

## Features

### AI-Powered Business Assessment

The application analyses a prospect's:

* Company
* Industry
* Product or service
* Business challenge
* Desired outcome
* Company size
* Geography
* Monthly process/customer volume
* Current team size
* Current tools and channels
* Current outsourcing/automation model
* Desired implementation timeline
* Selected improvement areas

The information is passed to the AI assessment engine to generate a company-specific transformation assessment.

---

## AI Opportunity Scoring

The platform generates a 0–100 opportunity score using five dimensions:

| Dimension              | Maximum Score |
| ---------------------- | ------------: |
| Problem Severity       |            20 |
| Operational Complexity |            20 |
| Aaspireya Service Fit  |            20 |
| Automation Potential   |            20 |
| Strategic / Growth Fit |            20 |
| **Total**              |       **100** |

Opportunity levels are classified as:

* **82–100:** High Potential
* **65–81:** Good Potential
* **45–64:** Potential Identified
* **0–44:** Early-Stage Opportunity

The final score is recalculated by the backend from the five dimensions rather than blindly trusting the LLM's supplied total.

---

## AI-Generated Assessment

The generated report can include:

* Executive diagnosis
* German executive summary
* Primary business challenges
* Transformation opportunities
* Business impact areas
* Recommended Aaspireya services
* AI and automation opportunities
* Recommended operating model
* Customer/operations channels
* KPI framework
* Implementation roadmap
* Recommended next step
* Client-facing call-to-action

The system is explicitly instructed not to invent unsupported company information, technology stacks, customer numbers, case studies, certifications or guaranteed ROI.

---

## AI + Human Operating Model

The recommended architecture follows a hybrid model:

```text
Customer / Business Input
          |
          v
       AI Triage
          |
     +----+----+
     |         |
     v         v
Automated    Human
Action       Expert
     |         |
     +----+----+
          |
          v
Resolution / Process Completion
          |
          v
      KPI + QA
          |
          v
Continuous Improvement
```

The purpose is not to replace human judgement completely.

Instead, suitable repetitive and structured activities can be automated or AI-assisted while complex cases, exceptions, escalation and human judgement remain with skilled personnel.

---

# System Architecture

```text
                        USER / PROSPECT
                              |
                              v
                    +--------------------+
                    |     FRONTEND       |
                    |    index.html      |
                    |                    |
                    | HTML / CSS / JS    |
                    +---------+----------+
                              |
                              | POST /api/chat
                              | JSON
                              v
                    +--------------------+
                    |    FLASK SERVER    |
                    |      app.py        |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | REQUEST VALIDATION |
                    |                    |
                    | JSON validation    |
                    | Required fields    |
                    | Email validation   |
                    | Input sanitisation |
                    | Service whitelist  |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    |  AI ORCHESTRATION  |
                    |                    |
                    | Prompt construction|
                    | Business context   |
                    | Service portfolio  |
                    | Analysis rules     |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    |     GEMINI LLM     |
                    |                    |
                    | Structured JSON    |
                    | assessment output  |
                    +---------+----------+
                              |
                       Success / Failure
                         /           \
                        /             \
                       v               v
              +---------------+  +---------------+
              | AI Response   |  | Fallback Model|
              | Processing    |  | / Engine      |
              +-------+-------+  +-------+-------+
                      |                 |
                      +--------+--------+
                               |
                               v
                    +--------------------+
                    | OUTPUT SANITISATION|
                    |                    |
                    | JSON validation    |
                    | Score validation   |
                    | Service validation |
                    | KPI validation     |
                    | Roadmap validation |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | ASSESSMENT ENGINE  |
                    |                    |
                    | 5 score dimensions |
                    | Opportunity score  |
                    | Opportunity level  |
                    +---------+----------+
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
        Web Report       Email Engine     WhatsApp CTA
        Rendering        SMTP / Resend    Lead Conversion
```

---

# Frontend Architecture

The frontend is implemented as a responsive single-page assessment experience.

## Main sections

1. Header
2. Hero section
3. Transformation snapshot
4. Trust/capability strip
5. How-it-works section
6. Five-step assessment form
7. Loading state
8. Dynamic AI report
9. WhatsApp CTA
10. Restart assessment
11. Footer

---

## Assessment Flow

```text
Step 1
Personal Information
        |
        v
Step 2
Company Information
        |
        v
Step 3
Improvement Areas
        |
        v
Step 4
Operating Context
        |
        v
Step 5
Review
        |
        v
Generate Assessment
```

The frontend performs client-side validation before sending the request.

---

# Backend Architecture

The backend is implemented using Python and Flask.

## Main responsibilities

* Serve the frontend
* Accept assessment submissions
* Validate incoming JSON
* Sanitise user input
* Validate email addresses
* Validate selected services
* Construct the AI prompt
* Call the Gemini REST API
* Parse structured JSON
* Validate and sanitise AI output
* Recalculate opportunity score
* Generate fallback assessments
* Generate HTML/text emails
* Send internal and client emails
* Generate WhatsApp conversion URLs
* Provide health diagnostics
* Return JSON API responses

---

# API Endpoints

## `GET /`

Returns the main assessment application.

---

## `GET /health`

Returns application and configuration health information.

Example:

```json
{
  "status": "ok",
  "gemini_configured": true,
  "gemini_model": "configured-model",
  "email_provider": "resend",
  "email_configured": true
}
```

---

## `POST /api/chat`

Main assessment endpoint.

### Request

```json
{
  "name": "Alexander Weber",
  "position": "Head of Customer Operations",
  "email": "alexander@example.com",
  "phone": "+49 171 1234567",
  "company": "Example GmbH",
  "product_type": "SaaS & Cloud Software",
  "product": "Enterprise SaaS platform",
  "selected_services": [
    "AI-Powered Automated Chat Assistant",
    "AI + Robotic Workflow Automation (RPA)"
  ],
  "query": "Our customer support team is handling a high volume of repetitive requests manually.",
  "company_size": "201–500 employees",
  "geography": "Germany / DACH",
  "monthly_volume": "20,000 tickets",
  "team_size": "25 support agents",
  "current_tools": "CRM, email and ticketing platform",
  "current_model": "Mostly handled in-house",
  "desired_outcome": "Reduce repetitive manual workload",
  "timeline": "1–3 months"
}
```

### Response

```json
{
  "success": true,
  "message": "Your Aaspireya Business Transformation Assessment has been generated.",
  "email_sent": true,
  "client_email_sent": true,
  "assessment": {},
  "whatsapp_url": "https://wa.me/..."
}
```

---

# AI Prompt Architecture

The AI prompt contains several layers.

## 1. Role Definition

The model is positioned as:

```text
Senior Enterprise Solutions Architect
and Business Transformation Consultant
```

## 2. Service Constraints

The model is given the exact Aaspireya service portfolio.

It is instructed to recommend only services from the predefined list.

## 3. Prospect Context

The prompt receives the structured prospect information collected through the frontend.

## 4. Analysis Rules

The model is instructed to:

* remain company-specific
* avoid generic BPO recommendations
* use the provided business context
* identify the actual workflow
* clearly identify missing information
* avoid unsupported claims
* avoid guaranteed ROI
* generate a five-dimensional opportunity score
* return valid JSON only

## 5. Structured Output

The expected JSON structure includes:

```text
report_title
opportunity_score
opportunity_level
industry_classification
urgency_rating
decision_focus
diagnosis_rationale
executive_summary
german_executive_summary
score_dimensions
primary_challenges
business_opportunities
business_impact_areas
solution_recommendation
automation_opportunities
recommended_channels
recommended_services
operational_diagram
kpi_framework
implementation_roadmap
recommended_next_step
cta_message
```

---

# AI Reliability Architecture

The system does not rely entirely on a successful LLM response.

```text
              Gemini Request
                    |
                    v
              Primary Model
                    |
              +-----+-----+
              |           |
           Success       Error
              |           |
              v           v
        Validate JSON   Fallback Model
              |           |
              |      +----+----+
              |      |         |
              |    Success    Error
              |      |         |
              +------+---------+
                     |
                     v
             Deterministic
             Fallback Engine
```

This allows the application to continue providing an assessment when the AI service is unavailable or returns an invalid response.

---

# Input Validation

The backend sanitises and validates incoming data before downstream processing.

Validation includes:

* Required field validation
* Email format validation
* String length limits
* Selected service whitelist validation
* Duplicate service removal
* Numeric score bounds
* JSON object validation
* Request payload limits

This reduces the risk of malformed data reaching the AI and email layers.

---

# Output Sanitisation

AI-generated output is also processed before being returned to the user.

The backend:

* validates that the response is a JSON object
* normalises score dimensions
* recalculates the total score
* assigns the correct opportunity level
* validates service names
* limits list sizes
* sanitises text lengths
* validates KPI objects
* validates roadmap objects
* provides defaults when required sections are missing

---

# Scoring Engine

The final score is calculated as:

```text
Opportunity Score =
    Problem Severity
  + Operational Complexity
  + Aaspireya Service Fit
  + Automation Potential
  + Strategic / Growth Fit
```

Each dimension:

```text
0–20
```

Total:

```text
0–100
```

The backend recalculates the score rather than trusting the total supplied by the AI.

---

# Fallback Assessment Engine

When Gemini is unavailable, the application uses deterministic business rules.

The fallback engine analyses the supplied data for indicators such as:

* urgency
* manual work
* automation
* repetitive workflows
* international operations
* CRM/ERP usage
* customer issues
* growth requirements
* operational complexity

It then generates a structured assessment using predefined Aaspireya capabilities.

---

# Email Architecture

The platform supports two email delivery approaches.

## SMTP

Useful for:

* Local development
* Gmail
* SMTP-enabled production environments

## Resend API

Useful for:

* Cloud deployment
* HTTPS-based email delivery
* Environments where outbound SMTP is restricted

---

# Email Workflow

```text
Assessment Submitted
        |
        v
AI Assessment Generated
        |
        v
Email Rendering
       / \
      /   \
     v     v
Internal  Client
Email     Email
```

The internal email contains submitted client information and the generated assessment.

The client email contains a client-facing version of the assessment.

Both email operations can be executed concurrently.

---

# WhatsApp Integration

After the assessment is generated, the backend creates a WhatsApp deep link containing:

* Company
* Industry
* AI Opportunity Score
* Conversation CTA

This provides a direct transition from:

```text
AI Assessment
      ↓
Business Opportunity
      ↓
WhatsApp Conversation
```

---

# Security Considerations

Current implementation includes:

* environment-based secrets
* input sanitisation
* email validation
* service whitelisting
* request size limits
* output escaping
* API error handling
* API timeout configuration

Secrets should never be committed to Git.

---

# Environment Variables

Example `.env` configuration:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_gemini_model
GEMINI_FALLBACK_MODELS=your_fallback_model

EMAIL_PROVIDER=smtp

SENDER_EMAIL=your_email@example.com
SENDER_PASSWORD=your_app_password

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=tls

TARGET_EMAIL=internal@example.com

WHATSAPP_NUMBER=country_code_number

GEMINI_TIMEOUT_SECONDS=8
EMAIL_TIMEOUT_SECONDS=8
```

For Resend:

```env
EMAIL_PROVIDER=resend
RESEND_API_KEY=your_resend_api_key
RESEND_FROM=verified_sender@example.com
```

---

# Installation

## 1. Clone the repository

```bash
git clone <repository-url>
cd aaspireya-ai-assessment
```

## 2. Create a virtual environment

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure environment variables

Create:

```text
.env
```

and add the required configuration.

## 5. Run locally

```bash
python app.py
```

The application runs on the configured Flask port.

---

# Production Deployment

The application can be deployed using Gunicorn.

Example:

```bash
gunicorn app:app
```

For Render, configure the appropriate build and start commands.

Typical start command:

```bash
gunicorn app:app
```

Production secrets should be configured through the hosting provider's environment variable system rather than committed to the repository.

---

# Project Structure

Current simplified structure:

```text
project/
│
├── app.py
├── requirements.txt
├── templates/
│   └── index.html
│
├── .env
└── README.md
```

Recommended future structure:

```text
project/
│
├── app.py
├── requirements.txt
├── README.md
├── .env
├── .gitignore
│
├── templates/
│   └── index.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── assessment.js
│
├── services/
│   ├── ai_service.py
│   ├── email_service.py
│   ├── scoring_service.py
│   └── whatsapp_service.py
│
├── utils/
│   ├── validation.py
│   └── sanitisation.py
│
├── config/
│   └── settings.py
│
└── tests/
    ├── test_api.py
    ├── test_scoring.py
    └── test_validation.py
```

---

# Technology Stack

## Frontend

* HTML5
* CSS3
* Vanilla JavaScript
* Fetch API
* Responsive design

## Backend

* Python
* Flask
* REST API
* Gunicorn

## AI

* Google Gemini API
* Prompt engineering
* Structured JSON generation
* LLM output validation
* AI fallback architecture
* Deterministic fallback assessment

## Communication

* SMTP
* Resend API
* WhatsApp deep links

## Deployment

* Render
* Gunicorn
* Environment variables

---

# Functional Flow

```text
1. Prospect visits assessment page
              ↓
2. Prospect completes five-step assessment
              ↓
3. Frontend validates information
              ↓
4. Frontend sends JSON to Flask
              ↓
5. Flask validates and sanitises request
              ↓
6. AI prompt is constructed
              ↓
7. Gemini generates structured assessment
              ↓
8. AI output is validated and sanitised
              ↓
9. Opportunity score is recalculated
              ↓
10. Assessment report is returned
              ↓
11. Internal email is generated
              ↓
12. Client email is generated
              ↓
13. WhatsApp CTA is created
              ↓
14. User sees personalised assessment
              ↓
15. Prospect can start a business conversation
```

---

# Error Handling

The application is designed to prevent common API failure modes from becoming confusing frontend errors.

For API requests, Flask returns JSON responses for errors such as:

* `400 Bad Request`
* `404 Not Found`
* `405 Method Not Allowed`
* `413 Payload Too Large`
* `500 Internal Server Error`

The frontend checks the response content type before parsing JSON and provides human-readable errors for non-JSON server responses.

---

# Production Considerations

The current application is suitable as a production-oriented MVP.

For higher traffic and enterprise usage, the following upgrades are recommended:

### Database

Add PostgreSQL for persistent storage of:

* leads
* assessments
* scores
* reports
* timestamps
* lead status

### Authentication

Add authenticated administration functionality.

### Admin Dashboard

Add:

* lead management
* assessment history
* score distribution
* high-potential leads
* conversion tracking
* filtering and search

### Rate Limiting

Protect the AI endpoint from abuse and unnecessary API consumption.

### Async Processing

Move AI and email operations into background workers for larger traffic volumes.

### Observability

Add:

* structured logging
* request IDs
* API latency monitoring
* AI latency monitoring
* email delivery monitoring
* error tracking

### Testing

Add automated tests for:

* validation
* scoring
* API responses
* fallback logic
* AI response sanitisation
* email generation

---

# Future Roadmap

## Phase 1 — Current MVP

* Responsive assessment platform
* Gemini AI integration
* Opportunity scoring
* AI report generation
* Email automation
* WhatsApp conversion
* Production deployment

## Phase 2 — Business Platform

* PostgreSQL
* Admin dashboard
* Lead history
* Authentication
* Analytics
* PDF report generation
* Lead status tracking
* CRM integration

## Phase 3 — Enterprise AI Platform

* Workflow-specific AI agents
* Retrieval-augmented generation
* Company knowledge bases
* CRM/ERP integrations
* Advanced workflow automation
* AI evaluation framework
* Model observability
* Human-in-the-loop review
* Automated lead prioritisation

---

# Business Value

The platform transforms a traditional business enquiry form into an AI-assisted consulting and lead qualification workflow.

Instead of:

```text
Form Submission
      ↓
Sales Team
      ↓
Manual Analysis
      ↓
Manual Follow-up
```

the platform enables:

```text
Business Input
      ↓
AI Analysis
      ↓
Opportunity Score
      ↓
Transformation Diagnosis
      ↓
Service Recommendations
      ↓
Automation Opportunities
      ↓
Implementation Roadmap
      ↓
Email + WhatsApp Follow-up
```

This can help Aaspireya:

* understand prospects more quickly
* standardise initial qualification
* provide a more personalised first interaction
* identify potential automation opportunities
* prioritise promising opportunities
* reduce repetitive pre-sales analysis
* create a more professional digital sales experience

---

# Resume Description

### Short Version

> Built and deployed an AI-powered business transformation assessment platform using Python, Flask, JavaScript and Gemini LLM, generating personalised opportunity scores, service recommendations, automation opportunities and implementation roadmaps from structured business inputs.

### Detailed Version

> Designed and deployed a production-oriented AI assessment platform using Flask and Gemini LLM, implementing structured prompt orchestration, JSON response validation, deterministic scoring, model/fallback logic, input sanitisation and automated report generation. Integrated SMTP/Resend email delivery and WhatsApp lead conversion while building a responsive multi-step assessment frontend and deploying the application using Gunicorn/Render.

---

# Project Classification

This project can be classified as:

**Applied Artificial Intelligence + Full-Stack Development + LLM Application Engineering + Business Automation**

It is not a machine-learning model training project.

It is an **AI-enabled production application** that integrates an LLM into a real business workflow.

---

# License

This project was developed specifically for Aaspireya Global Tech.

Commercial usage, redistribution and modification rights should be determined according to the agreement between the developer and Aaspireya Global Tech.
