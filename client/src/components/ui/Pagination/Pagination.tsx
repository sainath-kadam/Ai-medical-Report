import { FiChevronLeft, FiChevronRight } from 'react-icons/fi';
import './Pagination.css';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

type PageItem = number | 'ellipsis-start' | 'ellipsis-end';

function buildPageItems(page: number, totalPages: number): PageItem[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const items: PageItem[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);

  if (start > 2) items.push('ellipsis-start');
  for (let p = start; p <= end; p++) items.push(p);
  if (end < totalPages - 1) items.push('ellipsis-end');
  items.push(totalPages);

  return items;
}

export default function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;

  const items = buildPageItems(page, totalPages);

  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="pagination__nav"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
      >
        <FiChevronLeft size={16} />
      </button>

      {items.map((item, idx) =>
        typeof item === 'number' ? (
          <button
            key={item}
            type="button"
            className={`pagination__page ${item === page ? 'pagination__page--active' : ''}`}
            onClick={() => onPageChange(item)}
            aria-current={item === page ? 'page' : undefined}
          >
            {item}
          </button>
        ) : (
          <span key={`${item}-${idx}`} className="pagination__ellipsis">
            &hellip;
          </span>
        )
      )}

      <button
        type="button"
        className="pagination__nav"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        aria-label="Next page"
      >
        <FiChevronRight size={16} />
      </button>
    </nav>
  );
}
