const SIZE_CLASSES = {
  default: 'text-sm',
  compact: 'text-[12.5px] leading-relaxed',
};

export default function InlineAlert({ children, className = '', size = 'default' }) {
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.default;

  return (
    <p
      role="alert"
      className={`${sizeClass} font-medium ${className}`.trim()}
      style={{ color: 'var(--critical)' }}
    >
      {children}
    </p>
  );
}
