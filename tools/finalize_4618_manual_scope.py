from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'recepcion/app/reception_history_identity_consolidated.py'
text = p.read_text(encoding='utf-8-sig')

old_roots = "#modal .patient-profile-modal,.modal .patient-profile-modal,.patient-profile-modal,#modal .attention-form-modal,.modal .attention-form-modal,#modal .attention-form,#modal .modal-content,.modal .attention-form"
new_roots = "#modal .patient-profile-modal,.modal .patient-profile-modal,.patient-profile-modal,#modal .attention-form-modal,.modal .attention-form-modal,.attention-form-modal"
if text.count(old_roots) != 1:
    raise AssertionError(f'modal roots: expected 1 match, found {text.count(old_roots)}')
text = text.replace(old_roots, new_roots, 1)

old_gate = "        if(isSubsequent(body)){"
new_gate = "        if(isSubsequent(body)&&(()=>{try{return typeof attentionContext!=='undefined'&&!!attentionContext?.manualSubsequent}catch(_e){return false}})()){"
if text.count(old_gate) != 1:
    raise AssertionError(f'save gate: expected 1 match, found {text.count(old_gate)}')
text = text.replace(old_gate, new_gate, 1)

p.write_text(text, encoding='utf-8', newline='\n')
print('MANUAL_SCOPE_OK')
