import { useEffect, useRef, useState } from 'react';

const chapters = [
  { id: 'position', label: 'Position' },
  { id: 'four-tier-section', label: 'Portfolio' },
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'activity', label: 'Activity' },
];

export function ScrollStory({ children }) {
  const root = useRef(null);
  const [active, setActive] = useState('position');
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const container = root.current;
    if (!container) return undefined;
    const sections = chapters.map(({ id }) => container.querySelector(`#${id}`)).filter(Boolean);
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    const update = () => {
      frame = 0;
      const top = container.getBoundingClientRect().top + window.scrollY;
      const length = Math.max(container.offsetHeight - window.innerHeight, 1);
      setProgress(Math.min(1, Math.max(0, (window.scrollY - top) / length)));
      const current = [...sections].reverse().find((section) => section.getBoundingClientRect().top <= window.innerHeight * .42);
      setActive(current?.id ?? 'position');
    };
    const onScroll = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();

    let observer;
    if (!reduceMotion && 'IntersectionObserver' in window) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('story-visible');
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '0px 0px -8% 0px', threshold: .08 });
      container.querySelectorAll('[data-story-reveal]').forEach((element) => observer.observe(element));
    }
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (frame) window.cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, []);

  return <div className="scroll-story" ref={root}>
    <div className="story-progress" aria-hidden="true"><span style={{ transform: `scaleX(${progress})` }} /></div>
    <nav className="story-chapters" aria-label="Command Center sections">
      {chapters.map(({ id, label }, index) => <a key={id} href={`#${id}`} aria-current={active === id ? 'location' : undefined}>
        <span className="story-chapter-number">0{index + 1}</span>{label}
      </a>)}
    </nav>
    {children}
  </div>;
}
