user_prompts = {
    'genesis_question': 'Please give a quick summary of your complaint.'
}

model_prompts = {
    'generate_questions': '"""\n{complaint}\n"""\n\nGenerate a list of questions that an attorney would ask their client about this legal lawsuit.',
    'summarize_complaint': '"""\n{inquiries}\n"""\n\n{support_context}\n\nGenerate a long, litigation-ready summary of the plaintiff\'s complaint using only supported facts. Requirements:\n1) Use clear sections: Parties, Chronology, Alleged Violations, Evidence Map, Harm and Relief, and Open Factual Gaps.\n2) Prefer concrete dates, actors, notices, and communications when provided.\n3) If facts conflict (for example, different dates), keep both versions and label them as unresolved conflicts.\n4) If an answer is missing or vague, list it under Open Factual Gaps instead of speculating.\n5) Anchor key statements to available support context when possible (policies, records, legal references, or evidence repositories).\n6) Do not invent statutes, evidence, or events not present in the conversation/support context.\n7) End with a short Recommended Next Evidence Checklist tailored to the unresolved gaps.',
    'inquiry_block': 'Lawyer: {lawyer}\nPlaintiff: {plaintiff}'
}