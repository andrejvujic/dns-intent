import { useEffect, useMemo, useRef, useState } from 'react';

export const RECORD_TYPES = [
  'A',
  'AAAA',
  'CNAME',
  'MX',
  'TXT',
  'NS',
  'DS',
  'DNSKEY',
  'RRSIG',
  'NSEC',
  'NSEC3',
  'CAA',
];

const FIELD_DEFINITIONS = {
  A: [{ name: 'address', label: 'IPv4 address' }],
  AAAA: [{ name: 'address', label: 'IPv6 address' }],
  CNAME: [{ name: 'target', label: 'Target' }],
  MX: [
    { name: 'exchange', label: 'Mail server' },
    { name: 'priority', label: 'Priority', type: 'number' },
  ],
  TXT: [{ name: 'text', label: 'Text' }],
  NS: [{ name: 'host', label: 'Nameserver' }],
  DS: [
    { name: 'key_tag', label: 'Key tag', type: 'number' },
    { name: 'algorithm', label: 'Algorithm', type: 'number' },
    { name: 'digest_type', label: 'Digest type', type: 'number' },
    { name: 'digest', label: 'Digest' },
  ],
  DNSKEY: [
    { name: 'flags', label: 'Flags', type: 'number' },
    { name: 'protocol', label: 'Protocol', type: 'number' },
    { name: 'algorithm', label: 'Algorithm', type: 'number' },
    { name: 'public_key', label: 'Public key', wide: true },
  ],
  RRSIG: [
    { name: 'type_covered', label: 'Type covered' },
    { name: 'algorithm', label: 'Algorithm', type: 'number' },
    { name: 'labels', label: 'Labels', type: 'number' },
    { name: 'original_ttl', label: 'Original TTL', type: 'number' },
    { name: 'signature_expiration', label: 'Signature expiration', type: 'number' },
    { name: 'signature_inception', label: 'Signature inception', type: 'number' },
    { name: 'key_tag', label: 'Key tag', type: 'number' },
    { name: 'signer_name', label: 'Signer name' },
    { name: 'signature', label: 'Signature', wide: true },
  ],
  NSEC: [
    { name: 'next_domain_name', label: 'Next domain name' },
    { name: 'types', label: 'Record types', list: true, wide: true },
  ],
  NSEC3: [
    { name: 'hash_algorithm', label: 'Hash algorithm', type: 'number' },
    { name: 'flags', label: 'Flags', type: 'number' },
    { name: 'iterations', label: 'Iterations', type: 'number' },
    { name: 'salt', label: 'Salt' },
    { name: 'next_hashed_owner_name', label: 'Next hashed owner name' },
    { name: 'types', label: 'Record types', list: true, wide: true },
  ],
  CAA: [
    { name: 'flags', label: 'Flags', type: 'number' },
    { name: 'tag', label: 'Tag' },
    { name: 'value', label: 'Value' },
  ],
};

function initialValues(type, record) {
  const source = record?.value || {};
  const values = {
    name: record ? source.name ?? '' : '',
    ttl: record ? source.ttl ?? '' : '',
  };

  for (const field of FIELD_DEFINITIONS[type] || []) {
    const value = source[field.name];
    values[field.name] = field.list && Array.isArray(value)
      ? value.join(', ')
      : value ?? '';
  }

  return values;
}

function isValidIpv4(address) {
  const parts = address.split('.');
  return parts.length === 4 && parts.every((part) => (
    /^\d{1,3}$/.test(part) && Number(part) >= 0 && Number(part) <= 255
  ));
}

function isValidIpv6(address) {
  if (!/^[0-9a-f:]+$/i.test(address)) return false;
  const halves = address.split('::');
  if (halves.length > 2) return false;

  const segments = halves.flatMap((half) => (half ? half.split(':') : []));
  if (!segments.every((segment) => /^[0-9a-f]{1,4}$/i.test(segment))) return false;

  return halves.length === 2 ? segments.length < 8 : segments.length === 8;
}

function validate(type, values) {
  if (!type) return 'Type is required.';
  if (!String(values.name || '').trim()) return 'Name is required.';

  const ttl = Number(values.ttl);
  if (!Number.isInteger(ttl) || ttl < 0 || ttl > 2147483647) {
    return 'TTL must be a whole number between 0 and 2147483647.';
  }

  const address = String(values.address || '').trim();
  if (type === 'A' && address && !isValidIpv4(address)) {
    return 'Enter a valid IPv4 address.';
  }
  if (type === 'AAAA' && address && !isValidIpv6(address)) {
    return 'Enter a valid IPv6 address.';
  }

  for (const field of FIELD_DEFINITIONS[type] || []) {
    if (String(values[field.name] ?? '').trim() === '') {
      return `${field.label} is required.`;
    }

    if (field.type === 'number') {
      const numericValue = Number(values[field.name]);
      if (!Number.isSafeInteger(numericValue) || numericValue < 0) {
        return `${field.label} must be a non-negative whole number.`;
      }
    }

    if (field.list && !String(values[field.name]).split(',').some((item) => item.trim())) {
      return `${field.label} must contain at least one value.`;
    }
  }

  return '';
}

function buildValue(type, values) {
  const value = {
    name: String(values.name).trim(),
    ttl: Number(values.ttl),
  };

  for (const field of FIELD_DEFINITIONS[type] || []) {
    if (field.type === 'number') {
      value[field.name] = Number(values[field.name]);
    } else if (field.list) {
      value[field.name] = String(values[field.name])
        .split(',')
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean);
    } else {
      value[field.name] = String(values[field.name]).trim();
    }
  }

  return value;
}

function RecordTypeSelect({ value, types, disabled, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef(null);
  const triggerRef = useRef(null);
  const optionRefs = useRef([]);

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!containerRef.current?.contains(event.target)) setIsOpen(false);
    }

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  function openMenu() {
    if (disabled) return;
    const selectedIndex = types.indexOf(value);
    const nextIndex = selectedIndex >= 0 ? selectedIndex : 0;
    setActiveIndex(nextIndex);
    setIsOpen(true);
    window.requestAnimationFrame(() => optionRefs.current[nextIndex]?.focus());
  }

  function closeMenu({ returnFocus = false } = {}) {
    setIsOpen(false);
    if (returnFocus) window.requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function selectType(recordType) {
    onChange(recordType);
    closeMenu({ returnFocus: true });
  }

  function handleTriggerKeyDown(event) {
    if (['ArrowDown', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      openMenu();
    }
  }

  function handleOptionKeyDown(event, index) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      const nextIndex = (index + direction + types.length) % types.length;
      setActiveIndex(nextIndex);
      optionRefs.current[nextIndex]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      const nextIndex = event.key === 'Home' ? 0 : types.length - 1;
      setActiveIndex(nextIndex);
      optionRefs.current[nextIndex]?.focus();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenu({ returnFocus: true });
    }
  }

  return (
    <div className="type-select" ref={containerRef}>
      <button
        ref={triggerRef}
        className="type-select-trigger"
        type="button"
        aria-labelledby="record-type-label"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onClick={() => (isOpen ? closeMenu() : openMenu())}
        onKeyDown={handleTriggerKeyDown}
        disabled={disabled}
      >
        <span>{value || '\u00a0'}</span>
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="m6 8 4 4 4-4" />
        </svg>
      </button>

      {isOpen && (
        <div className="type-select-menu" role="listbox" aria-labelledby="record-type-label">
          {types.map((recordType, index) => (
            <button
              ref={(element) => { optionRefs.current[index] = element; }}
              className={`type-select-option${value === recordType ? ' selected' : ''}`}
              type="button"
              role="option"
              aria-selected={value === recordType}
              tabIndex={index === activeIndex ? 0 : -1}
              key={recordType}
              onClick={() => selectType(recordType)}
              onFocus={() => setActiveIndex(index)}
              onKeyDown={(event) => handleOptionKeyDown(event, index)}
            >
              {recordType}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DnsRecordForm({
  mode,
  record,
  availableTypes = RECORD_TYPES,
  isSubmitting,
  onSubmit,
  onClose,
  onNotify,
  kicker = 'DNS record',
  title,
  submitLabel,
}) {
  const isEdit = mode === 'edit';
  const [type, setType] = useState(record?.type || '');
  const [values, setValues] = useState(() => initialValues(record?.type || '', record));
  const firstInputRef = useRef(null);
  const fields = useMemo(() => FIELD_DEFINITIONS[type] || [], [type]);

  useEffect(() => {
    firstInputRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !isSubmitting) onClose();
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isSubmitting, onClose]);

  function updateField(name, value) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  function handleTypeChange(nextType) {
    setType(nextType);
    setValues(initialValues(nextType, null));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validate(type, values);
    if (message) {
      onNotify('error', message);
      return;
    }

    await onSubmit({
      ...(isEdit ? {} : { type }),
      value: buildValue(type, values),
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isSubmitting) onClose();
    }}>
      <section className="record-modal" role="dialog" aria-modal="true" aria-labelledby="record-form-title">
        <header className="modal-header">
          <div>
            <p className="modal-kicker">{kicker}</p>
            <h2 id="record-form-title">{title || (isEdit ? `Edit ${type} record` : 'Add record')}</h2>
          </div>
          <button className="modal-close" type="button" onClick={onClose} disabled={isSubmitting} aria-label="Close form">×</button>
        </header>

        <form className="record-form" onSubmit={handleSubmit} noValidate>
          <div className="form-grid">
            <div className="form-field">
              <span id="record-type-label">Type</span>
              {isEdit ? (
                <input value={type} readOnly aria-readonly="true" aria-labelledby="record-type-label" />
              ) : (
                <RecordTypeSelect value={type} types={availableTypes} onChange={handleTypeChange} disabled={isSubmitting} />
              )}
            </div>

            <label className="form-field">
              <span>Name</span>
              <input
                ref={firstInputRef}
                value={values.name}
                onChange={(event) => updateField('name', event.target.value)}
                disabled={isSubmitting}
                required
              />
            </label>

            <label className="form-field">
              <span>TTL</span>
              <input
                type="number"
                min="0"
                max="2147483647"
                step="1"
                value={values.ttl}
                onChange={(event) => updateField('ttl', event.target.value)}
                disabled={isSubmitting}
                required
              />
            </label>

            {fields.map((field) => (
              <label className={`form-field${field.wide ? ' form-field-wide' : ''}`} key={field.name}>
                <span>{field.label}</span>
                <input
                  type={field.type || 'text'}
                  step={field.type === 'number' ? '1' : undefined}
                  min={field.type === 'number' ? '0' : undefined}
                  value={values[field.name]}
                  onChange={(event) => updateField(field.name, event.target.value)}
                  disabled={isSubmitting}
                  required
                />
              </label>
            ))}
          </div>

          <footer className="modal-actions">
            <button className="button-secondary" type="button" onClick={onClose} disabled={isSubmitting}>Cancel</button>
            <button className="button-primary" type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : submitLabel || (isEdit ? 'Save changes' : 'Add record')}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
