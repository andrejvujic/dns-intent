// Users who registered themselves have no name yet, so show their email instead.
export function personName(person) {
  const full = [person.first_name, person.last_name].filter(Boolean).join(' ');
  return full || person.email || person.username || '';
}

export function personInitials(person) {
  const parts = [person.first_name, person.last_name].filter(Boolean);
  if (parts.length) return parts.map((part) => part[0]).join('').slice(0, 2).toUpperCase();
  return (person.email || '?')[0].toUpperCase();
}
