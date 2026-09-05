import { MouseEvent, ReactNode, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { FaUserMd } from 'react-icons/fa';
import {
  FiActivity,
  FiArrowRight,
  FiCheckCircle,
  FiCpu,
  FiFileText,
  FiLayers,
  FiMessageSquare,
  FiSearch,
  FiShield,
  FiUpload,
  FiUserCheck,
  FiUsers,
  FiZap,
} from 'react-icons/fi';
import { useScrollReveal } from '../../hooks/useScrollReveal';
import ThemeToggle from '../../components/common/ThemeToggle/ThemeToggle';
import './Landing.css';

const FEATURES = [
  {
    icon: FiCpu,
    title: 'AI-drafted reports in seconds',
    description: 'Upload a scan and get a structured, preliminary report drafted for physician review — no more starting from a blank page.',
  },
  {
    icon: FiLayers,
    title: 'Your templates, your format',
    description: 'Configure report sections, header, and branding once per organization; every AI draft follows it automatically.',
  },
  {
    icon: FiUsers,
    title: 'Role-based access, built in',
    description: 'Org admins and doctors see exactly what they should — every read and write is scoped to your organization, structurally.',
  },
  {
    icon: FiShield,
    title: 'Signed, time-limited file access',
    description: 'Imaging files are never served from a public URL — every link is signed and expires, and every action is audit-logged.',
  },
  {
    icon: FiActivity,
    title: 'X-ray, CT, MRI, ultrasound, DICOM',
    description: 'One workflow for every modality your practice handles, organized and stored by type.',
  },
  {
    icon: FiFileText,
    title: 'Versioned, amendable reports',
    description: 'Every edit creates a new version — nothing is overwritten. A finalized report is immutable; corrections become amendments.',
  },
];

const STEPS = [
  { icon: FiZap, title: 'Start your free trial', description: 'Sign up and get a 3-day trial — no credit card required.' },
  { icon: FiMessageSquare, title: 'Describe the patient & scan', description: 'A quick guided chat collects what’s needed — no rigid forms.' },
  { icon: FiCpu, title: 'AI drafts the findings', description: 'The imaging is analyzed and a structured preliminary report is generated.' },
  { icon: FiUserCheck, title: 'Review & finalize', description: 'A licensed physician reviews, edits if needed, and finalizes the report.' },
];

const SHOWCASE_ITEMS = [
  {
    key: 'chat',
    label: 'Conversational intake',
    icon: FiMessageSquare,
    img: '/landing/chat-intake.png',
    caption: 'Start a study by chatting — patient details, scan info, and report format. No rigid multi-page forms.',
  },
  {
    key: 'study',
    label: 'Study workspace',
    icon: FiUpload,
    img: '/landing/study-detail-full.png',
    caption: 'Everything about one study in one place — clinical history, files, patient context, and one-click AI analysis.',
  },
  {
    key: 'patients',
    label: 'Patient records',
    icon: FiSearch,
    img: '/landing/patients-list.png',
    caption: 'Search and manage every patient record in your organization, scoped to your team only.',
  },
];

function Reveal({ children, className = '' }: { children: ReactNode; className?: string }) {
  const { ref, isVisible } = useScrollReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={`landing-reveal ${isVisible ? 'landing-reveal--visible' : ''} ${className}`}>
      {children}
    </div>
  );
}

const SHOWCASE_INTERVAL_MS = 5000;

function ProductShowcase() {
  const [active, setActive] = useState(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setActive((a) => (a + 1) % SHOWCASE_ITEMS.length);
      setTick((t) => t + 1);
    }, SHOWCASE_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  function selectTab(i: number) {
    setActive(i);
    setTick((t) => t + 1);
  }

  return (
    <div className="landing-showcase">
      <div className="landing-showcase__tabs">
        {SHOWCASE_ITEMS.map((item, i) => (
          <button
            key={item.key}
            type="button"
            className={`landing-showcase__tab ${i === active ? 'landing-showcase__tab--active' : ''}`}
            onClick={() => selectTab(i)}
          >
            <item.icon size={15} />
            {item.label}
            {i === active && <span key={tick} className="landing-showcase__tab-progress" />}
          </button>
        ))}
      </div>

      <div className="landing-showcase__frame">
        <div className="landing-showcase__chrome">
          <span className="landing-showcase__dot landing-showcase__dot--red" />
          <span className="landing-showcase__dot landing-showcase__dot--yellow" />
          <span className="landing-showcase__dot landing-showcase__dot--green" />
          <div className="landing-showcase__url">app.medscan.ai</div>
        </div>
        <div className="landing-showcase__image-wrap">
          {SHOWCASE_ITEMS.map((item, i) => (
            <img
              key={item.key}
              src={item.img}
              alt={item.label}
              className={`landing-showcase__image ${i === active ? 'landing-showcase__image--active' : ''}`}
            />
          ))}
        </div>
      </div>

      <p className="landing-showcase__caption">{SHOWCASE_ITEMS[active].caption}</p>
    </div>
  );
}

export default function Landing() {
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    function onScroll() {
      setIsScrolled(window.scrollY > 8);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="landing">
      <header className={`landing-nav ${isScrolled ? 'landing-nav--scrolled' : ''}`}>
        <div className="landing-nav__brand">
          <span className="landing-nav__brand-mark">MS</span>
          <span>
            MedScan <strong>AI</strong>
          </span>
        </div>
        <div className="landing-nav__actions">
          <ThemeToggle />
          <Link to="/login" className="landing-nav__login">
            Log in
          </Link>
          <Link to="/signup">
            <button className="landing-btn landing-btn--primary landing-btn--sm">Start free trial</button>
          </Link>
        </div>
      </header>

      <section className="landing-hero">
        <div className="landing-hero__blobs" aria-hidden="true">
          <span className="landing-hero__blob landing-hero__blob--a" />
          <span className="landing-hero__blob landing-hero__blob--b" />
        </div>

        <div className="landing-hero__text">
          <span className="landing-hero__eyebrow">AI-assisted radiology reporting</span>
          <h1>
            From scan to structured report, <span className="landing-hero__accent">in seconds</span> — reviewed by a physician,
            always.
          </h1>
          <p>
            MedScan AI drafts a structured, preliminary imaging report the moment a scan is uploaded — so your team spends
            time reviewing and finalizing, not starting from a blank page.
          </p>
          <div className="landing-hero__actions">
            <Link to="/signup">
              <button className="landing-btn landing-btn--primary landing-btn--lg">
                Start your free trial <FiArrowRight size={16} />
              </button>
            </Link>
            <Link to="/login">
              <button className="landing-btn landing-btn--outline landing-btn--lg">Log in</button>
            </Link>
          </div>
          <p className="landing-hero__trust">Free 3-day trial · No credit card required</p>
        </div>

        <div className="landing-hero__visual" aria-hidden="true">
          <XrayPanel />
        </div>
      </section>

      <Reveal className="landing-stats">
        <div className="landing-stats__item">
          <FiZap size={20} />
          <span>Seconds, not hours, to a first draft</span>
        </div>
        <div className="landing-stats__item">
          <FiShield size={20} />
          <span>Every action audit-logged</span>
        </div>
        <div className="landing-stats__item">
          <FaUserMd size={20} />
          <span>Physician review, every time</span>
        </div>
      </Reveal>

      <section className="landing-section">
        <Reveal className="landing-section__header">
          <h2>See it in action</h2>
          <p>Real screens from the actual product — not mockups.</p>
        </Reveal>
        <Reveal>
          <ProductShowcase />
        </Reveal>
      </section>

      <section className="landing-section landing-section--alt">
        <Reveal className="landing-section__header">
          <h2>Everything a radiology team actually needs</h2>
          <p>No bloat — a focused workflow from upload to a finalized, physician-reviewed report.</p>
        </Reveal>
        <div className="landing-features">
          {FEATURES.map((feature, i) => (
            <Reveal key={feature.title} className="landing-feature-card">
              <div className="landing-feature-card__inner" style={{ transitionDelay: `${i * 60}ms` }}>
                <div className="landing-feature-card__icon">
                  <feature.icon size={20} />
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <Reveal className="landing-section__header">
          <h2>How it works</h2>
          <p>Four steps from a new patient to a finalized report.</p>
        </Reveal>
        <div className="landing-steps">
          {STEPS.map((step, i) => (
            <Reveal key={step.title} className="landing-step">
              <div className="landing-step__inner" style={{ transitionDelay: `${i * 80}ms` }}>
                <span className="landing-step__number">
                  <step.icon size={17} />
                </span>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <Reveal className="landing-cta">
        <span className="landing-cta__blob" aria-hidden="true" />
        <h2>Ready to see it on your own scans?</h2>
        <p>Start a free 3-day trial — set up takes less than two minutes.</p>
        <Link to="/signup">
          <button className="landing-btn landing-btn--primary landing-btn--lg">
            Start your free trial <FiArrowRight size={16} />
          </button>
        </Link>
      </Reveal>

      <footer className="landing-footer">
        <div className="landing-nav__brand">
          <span className="landing-nav__brand-mark">MS</span>
          <span>
            MedScan <strong>AI</strong>
          </span>
        </div>
        <div className="landing-footer__links">
          <Link to="/login">Log in</Link>
          <Link to="/signup">Sign up</Link>
        </div>
        <span className="landing-footer__copyright">© {new Date().getFullYear()} MedScan AI</span>
      </footer>
    </div>
  );
}

/** A self-contained SVG "viewer" panel with an animated scan sweep, two floating status
 *  cards, and a cursor-driven tilt — built as crisp, infinitely-scalable vector art (never
 *  blurry at any resolution or zoom, unlike a raster photo) rather than a stock/sourced
 *  photograph, which this codebase has no license to embed or hotlink. */
function XrayPanel() {
  const frameRef = useRef<HTMLDivElement>(null);

  function handleMouseMove(event: MouseEvent<HTMLDivElement>) {
    const el = frameRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    el.style.transform = `perspective(700px) rotateY(${x * 10}deg) rotateX(${-y * 10}deg)`;
  }

  function handleMouseLeave() {
    const el = frameRef.current;
    if (el) el.style.transform = 'perspective(700px) rotateY(0deg) rotateX(0deg)';
  }

  return (
    <div className="xray-panel" onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
      <div className="xray-panel__glow" />
      <div className="xray-panel__frame" ref={frameRef}>
        <svg viewBox="0 0 320 380" className="xray-panel__svg" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="ribGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(226,240,242,0.9)" />
              <stop offset="100%" stopColor="rgba(226,240,242,0.35)" />
            </linearGradient>
            <linearGradient id="scanGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(45,212,191,0)" />
              <stop offset="50%" stopColor="rgba(45,212,191,0.9)" />
              <stop offset="100%" stopColor="rgba(45,212,191,0)" />
            </linearGradient>
          </defs>

          {/* Spine */}
          <line x1="160" y1="30" x2="160" y2="350" stroke="url(#ribGradient)" strokeWidth="6" strokeLinecap="round" />

          {/* Ribcage */}
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <g key={i}>
              <path
                d={`M 160 ${70 + i * 38} C 110 ${72 + i * 38}, 78 ${95 + i * 38}, 74 ${130 + i * 38}`}
                fill="none"
                stroke="url(#ribGradient)"
                strokeWidth="5"
                strokeLinecap="round"
              />
              <path
                d={`M 160 ${70 + i * 38} C 210 ${72 + i * 38}, 242 ${95 + i * 38}, 246 ${130 + i * 38}`}
                fill="none"
                stroke="url(#ribGradient)"
                strokeWidth="5"
                strokeLinecap="round"
              />
            </g>
          ))}

          {/* Lungs (soft fill for contrast) */}
          <ellipse cx="112" cy="170" rx="34" ry="80" fill="rgba(45,212,191,0.06)" />
          <ellipse cx="208" cy="170" rx="34" ry="80" fill="rgba(45,212,191,0.06)" />

          {/* Pelvis hint */}
          <path d="M 110 330 Q 160 360 210 330" fill="none" stroke="url(#ribGradient)" strokeWidth="5" strokeLinecap="round" />
        </svg>

        <div className="xray-panel__scanline" />
        <div className="xray-panel__grid" />
      </div>

      <div className="xray-panel__badge xray-panel__badge--top">
        <span className="xray-panel__badge-dot" />
        AI analyzing…
      </div>
      <div className="xray-panel__badge xray-panel__badge--bottom">
        <FiCheckCircle size={14} />
        Report ready
      </div>
      <div className="xray-panel__doctor">
        <FaUserMd size={18} />
      </div>
    </div>
  );
}
