export default function PresentationScene({ children, number, className = '', ...props }) {
  return <section {...props} className={`apple-fullscreen-window ${className}`}>
    <div className="presentation-surface">
      <div className="presentation-atmosphere" aria-hidden="true">
        <span className="presentation-light light-one" /><span className="presentation-light light-two" />
        <svg viewBox="0 0 1440 900" preserveAspectRatio="none"><path d="M-100 680C290 180 370 920 810 460S1240 220 1540 340" /><path d="M-100 730C290 230 370 970 810 510S1240 270 1540 390" /><path d="M-100 780C290 280 370 1020 810 560S1240 320 1540 440" /></svg>
        <span className="presentation-number">{number}</span>
      </div>
      <div className="presentation-body">{children}</div>
    </div>
  </section>;
}
