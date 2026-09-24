"""Small browser-side form rules, shared by the wizard and fixture tests."""

WIZARD_SCAN_JS = r'''
                            return (function(answers) {
                                answers = answers || {};
                                var missed = [];

                                function getAns(key) {
                                    return (answers && answers[key]) ? answers[key] : null;
                                }

                                function findAnswer(labelText) {
                                    return window.diceAnswerFor(labelText, answers);
                                }

                                // Walk up the DOM up to maxDepth levels collecting ALL text
                                // from sibling elements, legend, label, p, h-tags, divs
                                // near the input — Dice puts question text in many different places.
                                function safeEscape(str) {
                                    if (!str) return '';
                                    try {
                                        if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(str);
                                    } catch(e){}
                                    return String(str).replace(/([\\"'#.:;?%&,<>=+*~^$\[\]{}()|\/\s])/g, '\\$1');
                                }

                                function getLabel(el) {
                                    // 1. Explicit <label for="id">
                                    if (el.id) {
                                        try {
                                            var lbl = document.querySelector('label[for="' + safeEscape(el.id) + '"]');
                                            if (lbl) return lbl.textContent.trim();
                                        } catch(e){}
                                    }
                                    // 2. aria-label
                                    var al = el.getAttribute('aria-label');
                                    if (al && al.trim()) return al.trim();
                                    // 3. aria-labelledby (may reference multiple ids)
                                    var alb = el.getAttribute('aria-labelledby');
                                    if (alb) {
                                        var labelParts = alb.split(/\s+/).map(function(id) {
                                            var el2 = document.getElementById(id);
                                            return el2 ? el2.textContent.trim() : '';
                                        }).filter(Boolean);
                                        if (labelParts.length) return labelParts.join(' ');
                                    }
                                    // 4. placeholder
                                    if (el.placeholder && el.placeholder.trim()) return el.placeholder.trim();
                                    // 5. Walk up DOM (up to 10 levels) checking various selectors
                                    var node = el;
                                    for (var d = 0; d < 10; d++) {
                                        node = node && node.parentElement;
                                        if (!node || node === document.body) break;
                                        // Check legend/label directly on this ancestor
                                        var direct = ['legend', 'label'].map(function(tag) {
                                            return node.tagName && node.tagName.toLowerCase() === tag ? node : null;
                                        }).filter(Boolean)[0];
                                        if (direct) {
                                            var t = direct.textContent.trim();
                                            if (t.length > 1) return t;
                                        }
                                        // Check child elements that look like question text
                                        var qsel = node.querySelectorAll(
                                            'legend, label, h1, h2, h3, h4, h5, h6, ' +
                                            'p, [class*="label"], [class*="question"], ' +
                                            '[class*="title"], [class*="heading"], ' +
                                            '[class*="field-name"], [class*="form-label"]'
                                        );
                                        for (var i = 0; i < qsel.length; i++) {
                                            var q = qsel[i];
                                            // Must not be the input itself, its container, or its child options
                                            if (q === el || q.contains(el) || el.contains(q) || q.tagName === 'OPTION' || q.closest('option')) continue;
                                            var qt = q.textContent
                                                .replace(/This field is required/gi, '')
                                                .replace(/\d+\s*\/\s*\d+/g, '')
                                                .replace(/\*\s*$/g, '')
                                                .trim();
                                            if (qt.length > 2 && qt.length < 250) return qt;
                                        }
                                    }
                                    // 6. Closest preceding sibling text as last resort
                                    var sib = el.previousElementSibling;
                                    if (sib) {
                                        var st = sib.textContent
                                            .replace(/This field is required/gi, '')
                                            .replace(/\*\s*$/g, '').trim();
                                        if (st.length > 2) return st.slice(0, 120);
                                    }
                                    return '';
                                }

                                // --- Native radio buttons ---
                                // Mark the VISIBLE click target (label or parent), not the hidden input.
                                // Selenium will do the actual click so React events fire correctly.
                                var radioGroups = {};
                                document.querySelectorAll('input[type="radio"]').forEach(function(radio) {
                                    if (!radio.offsetParent && getComputedStyle(radio).position !== 'absolute') return;
                                    var name = radio.name || radio.id || Math.random();
                                    if (!radioGroups[name]) radioGroups[name] = [];
                                    radioGroups[name].push(radio);
                                });
                                Object.keys(radioGroups).forEach(function(name) {
                                    var radios = radioGroups[name];
                                    // The radio's own label is an answer option, not the question.
                                    var fieldset = radios[0].closest('fieldset, [role="radiogroup"]');
                                    var legend = fieldset && fieldset.querySelector('legend');
                                    var groupLabel = legend ? legend.textContent.trim() :
                                        (fieldset ? getLabel(fieldset) : '');
                                    // If still no group label, try a common ancestor fieldset/legend
                                    if (!groupLabel) {
                                        var anc = radios[0].parentElement;
                                        for (var d = 0; d < 8 && anc; d++, anc = anc.parentElement) {
                                            var leg = anc.querySelector('legend, [class*="question"], [class*="label"]');
                                            if (leg && !leg.contains(radios[0])) { groupLabel = leg.textContent.trim(); break; }
                                        }
                                    }
                                    var answer = findAnswer(groupLabel);
                                    if (answer) {
                                        var matched = false;
                                        radios.forEach(function(r) {
                                            if (matched) return;
                                            // Find the visible click target for this option
                                            var clickTarget = null;
                                            var optText = '';
                                            var lbl = null;
                                            if (r.id) {
                                                try { lbl = document.querySelector('label[for="' + safeEscape(r.id) + '"]'); } catch(e){}
                                            }
                                            if (lbl) { optText = lbl.textContent.trim(); clickTarget = lbl; }
                                            else if (r.parentElement && r.parentElement.tagName === 'LABEL') {
                                                optText = r.parentElement.textContent.trim(); clickTarget = r.parentElement;
                                            } else if (r.nextElementSibling && r.nextElementSibling.tagName === 'LABEL') {
                                                optText = r.nextElementSibling.textContent.trim(); clickTarget = r.nextElementSibling;
                                            } else {
                                                optText = (r.value || r.getAttribute('data-value') || '').trim();
                                                clickTarget = r;
                                            }
                                            if (optText.toLowerCase() === answer.toLowerCase()) {
                                                clickTarget.setAttribute('data-dice-click', 'radio:' + answer);
                                                matched = true;
                                            }
                                        });
                                        if (!matched) missed.push('radio (no match): "' + groupLabel + '" → "' + answer + '"');
                                    } else {
                                        var anyChecked = radios.some(function(r) { return r.checked; });
                                        if (!anyChecked && groupLabel)
                                            missed.push('radio: "' + groupLabel + '"');
                                    }
                                });

                                // --- role="radio" / role="radiogroup" (Dice custom components) ---
                                document.querySelectorAll('[role="radiogroup"]').forEach(function(group) {
                                    if (!group.offsetParent) return;
                                    var groupLabel = getLabel(group);
                                    var answer = findAnswer(groupLabel);
                                    var opts = group.querySelectorAll('[role="radio"], [role="option"], button, label');
                                    if (answer && opts.length) {
                                        var matched = false;
                                        opts.forEach(function(opt) {
                                            if (matched) return;
                                            var t = opt.textContent.trim();
                                            if (t.toLowerCase() === answer.toLowerCase()) {
                                                opt.setAttribute('data-dice-click', 'radio-role:' + answer);
                                                matched = true;
                                            }
                                        });
                                        if (!matched && groupLabel)
                                            missed.push('role-radio (no match): "' + groupLabel + '" → "' + answer + '"');
                                    } else if (!answer && groupLabel) {
                                        missed.push('role-radio: "' + groupLabel + '"');
                                    }
                                });

                                // --- Standalone role="radio" items (outside explicit radiogroup) ---
                                document.querySelectorAll('[role="radio"]:not([role="radiogroup"] [role="radio"])').forEach(function(opt) {
                                    if (!opt.offsetParent) return;
                                    if (opt.hasAttribute('data-dice-click')) return; // already handled
                                    var groupLabel = getLabel(opt);
                                    var answer = findAnswer(groupLabel);
                                    if (!answer) {
                                        // Try parent container label
                                        var par = opt.parentElement;
                                        for (var d = 0; d < 5 && par; d++, par = par.parentElement) {
                                            var lbl2 = par.querySelector('label, [class*="label"], [class*="question"]');
                                            if (lbl2 && !lbl2.contains(opt)) { groupLabel = lbl2.textContent.trim(); break; }
                                        }
                                        answer = findAnswer(groupLabel);
                                    }
                                    if (answer) {
                                        var t = opt.textContent.trim();
                                        if (t.toLowerCase() === answer.toLowerCase()) {
                                            opt.setAttribute('data-dice-click', 'radio-role:' + answer);
                                        }
                                    }
                                });

                                // --- Button-group Yes/No (e.g. <button>Yes</button><button>No</button>) ---
                                // Look for containers that hold only Yes/No-style choices.
                                document.querySelectorAll(
                                    '[role="group"], [class*="toggle"], [class*="button-group"],' +
                                    '[class*="btn-group"], [class*="choice"], [class*="option-group"]'
                                ).forEach(function(group) {
                                    if (!group.offsetParent) return;
                                    var btns = group.querySelectorAll('button, [role="button"]');
                                    if (!btns.length || btns.length > 6) return; // skip huge menus
                                    var groupLabel = getLabel(group);
                                    var answer = findAnswer(groupLabel);
                                    if (answer && groupLabel) {
                                        var matched = false;
                                        btns.forEach(function(btn) {
                                            if (matched || btn.hasAttribute('data-dice-click')) return;
                                            var t = btn.textContent.trim();
                                            if (t.toLowerCase() === answer.toLowerCase()) {
                                                btn.setAttribute('data-dice-click', 'button:' + answer);
                                                matched = true;
                                            }
                                        });
                                    }
                                });

                                // --- Select dropdowns ---
                                // Mark for Python Selenium Select class — JS dispatchEvent doesn't
                                // reliably trigger React's synthetic onChange handler.
                                document.querySelectorAll('select').forEach(function(sel) {
                                    if (!sel.offsetParent) return; // hidden
                                    if (sel.value && sel.value !== '') return; // already selected
                                    var labelText = getLabel(sel);
                                    var answer = findAnswer(labelText);
                                    if (answer) {
                                        sel.setAttribute('data-dice-select', answer);
                                    } else if (labelText) {
                                        missed.push('select: "' + labelText + '"');
                                    }
                                });

                                // --- Text / number / email / textarea inputs ---
                                // Mark matched fields with data-dice-fill so Python send_keys
                                // can type real keyboard events into them (React requires this).
                                // ALL visible empty fields are checked — not just required ones —
                                // because Dice often omits the required attribute on custom questions.
                                document.querySelectorAll(
                                    'input:not([type]), input[type="text"], input[type="number"], input[type="email"],' +
                                    'input[type="tel"], input[type="url"], textarea'
                                ).forEach(function(inp) {
                                    if (!inp.offsetParent) return; // skip hidden
                                    if (inp.value && inp.value.trim() !== '') return; // already filled
                                    var labelText = getLabel(inp);
                                    var answer = findAnswer(labelText);
                                    if (answer) {
                                        inp.setAttribute('data-dice-fill', answer);
                                        inp.setAttribute('data-dice-label', (labelText || 'field').slice(0, 80));
                                    } else {
                                        // Flag ALL empty visible fields for Groq, not just required ones
                                        var label = labelText || inp.placeholder || inp.name || '';
                                        if (label)
                                            missed.push('input: "' + label + '"');
                                    }
                                });

                                return missed;
                            })(arguments[0]);
                        '''

ANSWER_MATCHER_JS = r'''
window.diceAnswerFor = function(label, answers) {
    const questionNorm = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim().replace(/\*+$/, '').trim();
    const question = questionNorm(label);
    if (Object.prototype.hasOwnProperty.call(window.diceApprovedAnswers || {}, question)) return window.diceApprovedAnswers[question];
    if ((window.diceManagedQuestions || []).includes(question)) return null;
    const norm = s => String(s || '').toLowerCase().trim().replace(/\s+/g, ' ');
    const text = norm(label);
    const keys = Object.keys(answers || {}).filter(k => norm(k) && answers[k]);
    const exact = keys.find(k => norm(k) === text);
    if (exact) return answers[exact];
    const genericExperience = new Set(['experience', 'years of experience', 'how many years', 'years of relevant experience']);
    const matches = keys.filter(k => {
        const pattern = norm(k);
        if (!text.includes(pattern)) return false;
        // A total-experience number must not answer an unspecified skill-specific question.
        if (genericExperience.has(pattern) && /experience|years/.test(text)) return false;
        // Avoid 'visa' matching part of another word.
        const at = text.indexOf(pattern);
        return (at === 0 || !/[a-z0-9]/.test(text[at-1])) &&
               (at + pattern.length === text.length || !/[a-z0-9]/.test(text[at+pattern.length]));
    }).sort((a,b) => norm(b).length - norm(a).length);
    if (!matches.length) return null;
    const best = matches.filter(k => norm(k).length === norm(matches[0]).length);
    if (new Set(best.map(k => norm(answers[k]))).size > 1) return null;
    return answers[matches[0]];
};
'''

SUBMIT_REVIEW_JS = r'''
return (() => {
    const visible = el => !!(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
    const label = el => {
        if (el.labels && el.labels.length) return el.labels[0].textContent.trim();
        const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/);
        const named = ids.map(id => document.getElementById(id)).filter(Boolean).map(n => n.textContent.trim()).join(' ');
        const group = el.closest('fieldset, [role=radiogroup]');
        return named || el.getAttribute('aria-label') ||
            (group && group.querySelector('legend') && group.querySelector('legend').textContent.trim()) ||
            el.getAttribute('placeholder') || el.name || 'Unlabelled field';
    };
    const values = [];
    const seenRadios = new Set();
    document.querySelectorAll('input, textarea, select').forEach(el => {
        if (!visible(el) || el.disabled || ['hidden','submit','button','reset','password'].includes(el.type)) return;
        if (el.type === 'radio') {
            const key = el.name || el.id;
            if (seenRadios.has(key)) return;
            seenRadios.add(key);
            const group = el.closest('fieldset, [role=radiogroup]');
            const legend = group && group.querySelector('legend');
            const question = (legend && legend.textContent.trim()) ||
                (group && group.getAttribute('aria-label')) || el.name || label(el);
            const choices = Array.from(document.querySelectorAll('input[type=radio]'))
                .filter(r => !r.disabled && r.name === el.name && r.form === el.form);
            const checked = choices.find(r => r.checked);
            values.push({question, answer: checked ? label(checked) : 'Not selected', type: 'radio'});
            return;
        }
        if (el.type === 'file') {
            values.push({question: label(el), answer: el.files && el.files.length ?
                Array.from(el.files).map(f => f.name).join(', ') : 'No file selected', type: 'file'});
            return;
        }
        const answer = el.type === 'checkbox' ? (el.checked ? 'Checked' : 'Not checked') :
            el.tagName === 'SELECT' ? (el.selectedOptions[0] ? el.selectedOptions[0].textContent.trim() : '') :
            String(el.value || '').trim();
        values.push({question: label(el), answer: answer || 'Blank', type: el.type || 'text'});
    });
    return values;
})();
'''

REVIEW_FIELDS_JS = r'''
return (() => {
    const visible = el => !!(el.getClientRects().length) && !el.disabled && !el.matches(':disabled') && getComputedStyle(el).visibility !== 'hidden';
    const label = el => {
        if (el.labels && el.labels.length) return el.labels[0].textContent.trim();
        const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
            .map(id => document.getElementById(id)).filter(Boolean).map(e => e.textContent.trim()).join(' ');
        if (labelled) return labelled;
        const direct = el.getAttribute('aria-label') || el.placeholder;
        if (direct) return direct;
        const legend = el.querySelector && el.querySelector(':scope > legend');
        if (legend) return legend.textContent.trim();
        // Only use a nearby question label within a single-field container.
        let parent = el.parentElement;
        for (let depth = 0; parent && depth < 3; depth++, parent = parent.parentElement) {
            if (parent.querySelectorAll('input:not([type=hidden]), textarea, select, [role=radiogroup]').length > 1) break;
            const heading = parent.querySelector('label, legend, [class*=question], [class*=label]');
            if (heading) return heading.textContent.trim();
        }
        return el.name || '';
    };
    const state = (el, question) => {
        const group = el.closest('fieldset, [role=radiogroup], [role=group]');
        const explicitRequired = node => node && (node.required || node.getAttribute('aria-required') === 'true' || node.getAttribute('data-required') === 'true');
        const invalid = el.getAttribute('aria-invalid') === 'true' ||
            !!(el.validity && !el.validity.valid) || !!(group && group.getAttribute('aria-invalid') === 'true');
        const errorIds = (el.getAttribute('aria-errormessage') || '').split(/\s+/);
        const ids = errorIds.concat((el.getAttribute('aria-describedby') || '').split(/\s+/));
        const messages = ids.map(id=>document.getElementById(id)).filter(node=>node && visible(node) &&
            (invalid || errorIds.includes(node.id) || node.getAttribute('role') === 'alert' || /error|invalid/i.test(node.className || '')))
            .map(node=>node.textContent.trim()).filter(Boolean);
        return {
            required: !!(explicitRequired(el) || explicitRequired(group) || /\*|\(\s*required\s*\)|\[\s*required\s*\]|\brequired\s*$/i.test(question)),
            invalid: invalid || messages.length > 0,
            validation_message: messages.join(' ') || (invalid ? el.validationMessage || 'The page marked this field invalid.' : '')
        };
    };
    const result = [];
    document.querySelectorAll('input:not([type=radio]):not([type=hidden]):not([type=submit]):not([type=button]), textarea, select')
    .forEach(el => {
        if (!visible(el)) return;
        const question = label(el) || 'Unlabelled field';
        const validation = state(el, question);
        const filled = el.type === 'checkbox' ? el.checked : String(el.value || '').trim();
        if (!validation.invalid && filled) return;
        result.push({question, field_type: el.tagName === 'SELECT' ? 'select' : el.type || 'text',
            ...validation,
            options: el.options ? Array.from(el.options).filter(o=>!o.disabled && o.value).map(o=>o.text.trim()) : []});
    });
    const seen = new Set();
    document.querySelectorAll('input[type=radio]').forEach(el => {
        const key = el.name || el;
        if (el.disabled || seen.has(key)) return;
        seen.add(key);
        const radios = Array.from(document.querySelectorAll('input[type=radio]')).filter(r=>!r.disabled && (el.name ? r.name===el.name && r.form===el.form : r===el));
        const parent = el.closest('fieldset, [role=radiogroup]') || el.parentElement;
        if (!parent || !visible(parent)) return;
        const legend = parent.querySelector('legend');
        const question = legend ? legend.textContent.trim() : label(parent) || label(el);
        const states = radios.map(r=>state(r, question));
        if (radios.some(r=>r.checked) && !states.some(s=>s.invalid)) return;
        result.push({question:question || 'Unlabelled radio group', field_type:'radio', required:states.some(s=>s.required),
            invalid:states.some(s=>s.invalid), validation_message:states.map(s=>s.validation_message).filter(Boolean).join(' '), options:radios.map(label)});
    });
    document.querySelectorAll('[role=radiogroup]').forEach(group => {
        if (!visible(group) || group.querySelector('input[type=radio]')) return;
        const question = label(group);
        const validation = state(group, question);
        if (!validation.invalid && group.querySelector('[aria-checked=true], input:checked, [aria-selected=true]')) return;
        if (question) result.push({question, field_type:'radio', ...validation,
            options:Array.from(group.querySelectorAll('[role=radio]')).map(e=>e.textContent.trim())});
    });
    document.querySelectorAll('[role=group], [class*=toggle], [class*=button-group], [class*=btn-group], [class*=choice], [class*=option-group]').forEach(group => {
        if (!visible(group) || group.querySelector('input, select, textarea, [role=radio]')) return;
        const choices = Array.from(group.querySelectorAll('button, [role=button]'));
        if (choices.length !== 2 || !choices.every(e=>/^(yes|no)$/i.test(e.textContent.trim()))) return;
        const question = label(group);
        const validation = state(group, question);
        if (!validation.invalid && choices.some(e=>e.getAttribute('aria-pressed')==='true' || e.getAttribute('aria-selected')==='true')) return;
        if (question) result.push({question, field_type:'radio', ...validation, options:choices.map(e=>e.textContent.trim())});
    });
    return result;
})();
'''
