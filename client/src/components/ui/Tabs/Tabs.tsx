import { ReactNode } from 'react';
import './Tabs.css';

export interface TabItem {
  key: string;
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
}

interface TabsProps {
  items: TabItem[];
  activeKey: string;
  onChange: (key: string) => void;
}

/** Generic tab strip -- the caller owns which key is active and renders whatever panel
 *  content goes with it; this component is only the clickable strip itself. */
export default function Tabs({ items, activeKey, onChange }: TabsProps) {
  return (
    <div className="ui-tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={item.key === activeKey}
          className={`ui-tabs__tab ${item.key === activeKey ? 'ui-tabs__tab--active' : ''}`}
          onClick={() => onChange(item.key)}
        >
          {item.icon}
          <span>{item.label}</span>
          {item.badge}
        </button>
      ))}
    </div>
  );
}
