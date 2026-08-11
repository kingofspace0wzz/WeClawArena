# CM-D-claw_clinical__t6 Context

Family: claw_clinical
Scenario: claw_clinical_cardio_referral_CM-D-claw_clinical__t6
Role: specialist

Task prompt:
Dr. Martinez, patient James Okafor (age 58) presents with: Exertional chest pain, new onset, 3 weeks duration, relieved by rest. Relevant history: Hypertension (controlled, lisinopril 20mg); Type 2 diabetes (metformin 1000mg BID); Family history: father MI at age 52. Current medications: Lisinopril 20mg daily, Metformin 1000mg BID, Aspirin 81mg daily, and 1 more.

Based on the clinical presentation, a referral to Cardiology appears indicated. Coordinate with the care team: have the specialist evaluate, pharmacist review current medications for any concerns with the transition, insurance verify coverage, and nurse schedule the appointment once approved.

Task completion requirements: Attending should call request_referral with the patient_id and specialty. Insurance and nurse may complete preauth and scheduling, but the task success check requires the referral to be tool-recorded. Stop once the referral is submitted.

Structured identifiers:
- patient_id: PT-30872
- specialty: Cardiology

Boundary notes:
- Use the task identifiers exactly as written.
- Keep private patient or portfolio fields out of public messages.
- Record final task progress through the required tool call.
