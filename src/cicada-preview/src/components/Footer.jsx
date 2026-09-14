export default function Footer() {
  return (
    <footer className="border-t py-6" style={{ borderColor: 'var(--line)' }}>
      <p className="max-w-3xl mx-auto px-6 text-[11.5px] leading-relaxed" style={{ color: 'var(--ink-faint)' }}>
        MedTrust Connect is a support tool, not a diagnosis. Quick-check results are informational
        only, generated from FDA label data and a deterministic rule engine — they have{' '}
        <strong>not</strong> been reviewed by a licensed pharmacist. Always follow your care team's
        direction, and call emergency services for anything urgent.
      </p>
    </footer>
  );
}
