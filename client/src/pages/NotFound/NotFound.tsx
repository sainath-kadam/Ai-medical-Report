import { Link } from 'react-router-dom';
import { FiArrowLeft } from 'react-icons/fi';
import Button from '../../components/common/Button/Button';
import './NotFound.css';

export default function NotFound() {
  return (
    <div className="not-found-page">
      <span className="not-found-page__code">404</span>
      <h1>Page not found</h1>
      <p>The page you&apos;re looking for doesn&apos;t exist or may have been moved.</p>
      <Link to="/">
        <Button icon={<FiArrowLeft size={16} />}>Back to dashboard</Button>
      </Link>
    </div>
  );
}
