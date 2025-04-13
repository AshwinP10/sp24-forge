from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import PyPDF2
import re
import uuid
from werkzeug.utils import secure_filename
from google import genai

# Flask configuration
app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['GOOGLE_API_KEY'] = "ENTER HERE"

# Initialize Gemini client
client = genai.Client(api_key=app.config['GOOGLE_API_KEY'])

# Create folders if needed
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text
    except Exception as e:
        print(f"Error extracting text: {e}")
        return f"Error extracting text: {str(e)}"

def evaluate_document_with_decision_tree(text):
    try:
        max_length = 30000
        if len(text) > max_length:
            text = text[:max_length] + "..."

        decision_tree = """[---

## GENERAL QUESTIONS (All Vendors)

1. Are you submitting a new offer or a streamlined modification?
- Yes → Proceed
- No → STOP (Documents may not be applicable)

2. Do you have an active SAM registration?
- Yes → Upload SAM Registration Confirmation
- No → Must register before proceeding

3. Are you offering products, services, or both?
- Products → Proceed to Section A (Product Documents)
- Services or Training → Proceed to Section B (Service Documents)
- Both → Complete both Section A and B

4. Have you completed the Pathways to Success Training?
- Yes → Continue
- No → Must complete training before proceeding

5. Have you completed the Readiness Assessment?
- Yes → Continue
- No → Must complete before proceeding

6. Are you a joint venture?
- Yes → Joint Venture Solicitation Attachment required
- No → Proceed

7. Do you have a Quality Control Plan (QCP)?
- Yes → Upload or input QCP using GSA-required headers
- No → QCP required; if help needed, contact Coley GCS

8. Do you employ professionals covered under FAR 52.222-46?
- Yes → Provide a Professional Compensation Plan (PCP)
- No → PCP still required with responses under required headers

9. Do you utilize uncompensated overtime?
- Yes → Submit Uncompensated Overtime Policy
- No → Must still respond to the policy requirement

10. Have you previously had a GSA contract canceled?
- Yes → Submit cancellation notice and response
- No → Proceed

11. Have you previously had an offer rejected?
- Yes → Submit Previous Rejections Response
- No → Proceed

12. Are you considered a large business by the SBA under your primary NAICS code?
- Yes → Provide Subcontracting Plan
- No → Proceed and revisit if applicable

13. Have you completed Pricing Terms?
- Yes → Provide fill-in responses or upload Pricing Terms Sheet
- No → Proceed and revisit later

14. Have you completed Commercial Sales Practice information?
- Yes → Provide CSP information
- No → Proceed and revisit later

15. Can you substantiate all proposed products/services?
- Yes → Provide invoices, price lists, market research, or surveys
- No → Proceed and revisit later

---

## SECTION A: PRODUCT-SPECIFIC DOCUMENTS

1. Are your products manufactured in the U.S. or a TAA-compliant country?
- Yes → Submit TAA Compliance Document
- No → Not eligible for GSA contract

2. Are you providing off-the-shelf products or are you a reseller?
- Yes → Check if supplier is in Verified Products Portal
    - If Yes → No Letter of Supply needed
    - If No → Letter of Supply required
- If manufacturer → Proceed

3. Do you provide software?
- Yes → Submit End User License Agreement (EULA)
- No → Proceed

4. Do your products require Section 508 compliance?
- Yes → Submit Section 508 Compliance Acknowledgment
- No → Proceed

5. Are your products under the AbilityOne program?
- Yes → Submit AbilityOne Compliance Statement
- No → Proceed

6. Do you have a commercial price list or market rate sheet?
- Yes → Upload commercial price list
  - If a reseller, upload manufacturer's price list too
- No → Generate one using price proposal templates

---

## SECTION B: SERVICE-SPECIFIC DOCUMENTS

1. Can you provide 3+ Past Performance Questionnaires or CPARS?
- Yes → Upload CPARS and/or 3–5 Questionnaires
- No → May qualify for GSA Springboard (provide link and note to call team)

2. Are you submitting pricing for services?
- Yes → Complete Price Narrative and Pricing Proposal Templates
- No → Proceed

3. Are you providing labor categories covered under the Service Contract Act?
- Yes → Complete Labor Matrix
- No → Proceed

---

## FINAL CHECK: ADDITIONAL COMPLIANCE

1. Are you using a third-party agent for negotiations or post-award actions?
- Yes → Submit Agent Authorization Letter
- No → Proceed

2. Are you requesting continuous contracts or streamlining modifications?
- Yes → Submit Request to Hold Continuous Contracts
- No → Proceed

3. Are your products free of single-use plastics (SUP)?
- Yes → Submit GSAR 552.238-118 SUP-Free Packaging Identification
- No → Proceed

4. Do you have exceptions to standard certifications and reps?
- Yes → Submit Justification for Exceptions
- No → Acknowledge full compliance

---]"""

        prompt = f"""
Given the following extracted text from PDF documents, evaluate it based on the decision tree criteria.

{decision_tree}

--- COMBINED PDF TEXT ---
{text}

Please classify this submission as 'Accepted' or 'Not Accepted' based on the decision tree. Be very strict and and provide a brief curt explanation as to what's missing and needs to be completed/confirmed before acceptance and things to watch for.
"""

        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )

        return response.text
    except Exception as e:
        print(f"Error evaluating document: {e}")
        return f"Error evaluating document: {str(e)}"

def save_text_to_temp_file(text, evaluation=None):
    text_id = str(uuid.uuid4())
    file_path = os.path.join(app.config['TEMP_FOLDER'], f"{text_id}.txt")
    eval_path = os.path.join(app.config['TEMP_FOLDER'], f"{text_id}_evaluation.txt")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)

    if evaluation:
        with open(eval_path, 'w', encoding='utf-8') as f:
            f.write(evaluation)

    return text_id

def get_text_from_temp_file(text_id, is_evaluation=False):
    suffix = "_evaluation.txt" if is_evaluation else ".txt"
    file_path = os.path.join(app.config['TEMP_FOLDER'], f"{text_id}{suffix}")

    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash('No files selected')
        return redirect(url_for('index'))

    combined_text = ""
    uploaded_filenames = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            uploaded_filenames.append(filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            extracted_text = extract_text_from_pdf(file_path)
            combined_text += f"\n\n--- Extracted from: {filename} ---\n\n{extracted_text}"

            os.remove(file_path)
        else:
            flash(f"Unsupported file skipped: {file.filename}")

    if not combined_text.strip():
        flash("No valid text extracted from uploaded PDFs.")
        return redirect(url_for('index'))

    evaluation = evaluate_document_with_decision_tree(combined_text)
    text_id = save_text_to_temp_file(combined_text, evaluation)

    session['text_id'] = text_id
    session['filename'] = ", ".join(uploaded_filenames)

    return redirect(url_for('results'))

@app.route('/results')
def results():
    if 'text_id' not in session or 'filename' not in session:
        flash('No text to display. Please upload a PDF file first.')
        return redirect(url_for('index'))

    text_id = session['text_id']
    extracted_text = get_text_from_temp_file(text_id)
    evaluation = get_text_from_temp_file(text_id, is_evaluation=True)

    if extracted_text is None:
        flash('The extracted text has expired. Please upload the PDF file again.')
        return redirect(url_for('index'))

    return render_template('results.html',
                           text=extracted_text,
                           summary=evaluation,
                           filename=session['filename'],
                           text_id=text_id)

@app.route('/cleanup/<text_id>')
def cleanup(text_id):
    file_path = os.path.join(app.config['TEMP_FOLDER'], f"{text_id}.txt")
    eval_path = os.path.join(app.config['TEMP_FOLDER'], f"{text_id}_evaluation.txt")

    if os.path.exists(file_path):
        os.remove(file_path)
    if os.path.exists(eval_path):
        os.remove(eval_path)

    session.pop('text_id', None)
    session.pop('filename', None)

    return redirect(url_for('index'))

@app.before_request
def cleanup_old_files():
    import time
    now = time.time()
    for fname in os.listdir(app.config['TEMP_FOLDER']):
        fpath = os.path.join(app.config['TEMP_FOLDER'], fname)
        if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 3600:
            os.remove(fpath)

if __name__ == '__main__':
    app.run(debug=True)
