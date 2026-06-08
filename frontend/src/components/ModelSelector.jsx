import { useState, useEffect } from 'react';
import { api } from '../api';
import './ModelSelector.css';

const CLI_OPTIONS = [
  { id: 'claude', label: 'Claude' },
  { id: 'codex', label: 'GPT (Codex)' },
  { id: 'gemini', label: 'Gemini' },
  { id: 'agy', label: 'Antigravity' },
];

const DEFAULT_SENTINEL = '(default)';

/**
 * Configure the council line-up: which CLI + which model for each member,
 * plus the chairman. Model lists are dynamic (agy is live; the rest are
 * free-text). Leaving a model blank uses that CLI's auto-updating default,
 * whose currently-resolved value is shown as the placeholder.
 */
export default function ModelSelector({ council, onChange, onClose }) {
  const [models, setModels] = useState({}); // {cli: {models, live}}
  const [status, setStatus] = useState({}); // {cli: {available, default_model}}

  useEffect(() => {
    api.getModels().then(setModels).catch((e) => console.error('getModels', e));
    api
      .getAgentsStatus()
      .then((list) => {
        const map = {};
        list.forEach((a) => (map[a.id] = a));
        setStatus(map);
      })
      .catch((e) => console.error('getAgentsStatus', e));
  }, []);

  const modelsFor = (cli) => models[cli]?.models || [];
  const defaultFor = (cli) => status[cli]?.default_model || DEFAULT_SENTINEL;

  const updateMember = (idx, patch) => {
    const members = council.members.map((m, i) => (i === idx ? { ...m, ...patch } : m));
    onChange({ ...council, members });
  };

  const removeMember = (idx) => {
    onChange({ ...council, members: council.members.filter((_, i) => i !== idx) });
  };

  const addMember = () => {
    onChange({ ...council, members: [...council.members, { cli: 'claude', model: null }] });
  };

  const updateChairman = (patch) => {
    onChange({ ...council, chairman: { ...council.chairman, ...patch } });
  };

  const modelValue = (model) => (model == null || model === '' ? '' : model);
  const onModelInput = (value) => (value.trim() === '' ? null : value);

  const renderModelField = (cli, model, onPick) => (
    <div className="model-field">
      <input
        list={`models-${cli}`}
        className="model-input"
        value={modelValue(model)}
        placeholder={defaultFor(cli)}
        onChange={(e) => onPick(onModelInput(e.target.value))}
      />
      <datalist id={`models-${cli}`}>
        {modelsFor(cli).map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
    </div>
  );

  const cliSelect = (cli, onPick) => (
    <select className="cli-select" value={cli} onChange={(e) => onPick(e.target.value)}>
      {CLI_OPTIONS.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
          {status[o.id]?.available === false ? ' (not installed)' : ''}
        </option>
      ))}
    </select>
  );

  return (
    <div className="model-selector glass">
      <div className="ms-header">
        <span className="ms-title">Council line-up</span>
        <button className="ms-close" onClick={onClose} title="Close">
          ×
        </button>
      </div>

      <div className="ms-hint">
        Models are dynamic and auto-update. Leave a model blank for{' '}
        <code>(default)</code> — the placeholder shows what it resolves to right now. Only
        Antigravity (agy) lists models live; for the others, type any model name.
      </div>

      <div className="ms-section-label">Members</div>
      {council.members.map((m, idx) => (
        <div className="ms-row" key={idx}>
          {cliSelect(m.cli, (cli) => updateMember(idx, { cli, model: null }))}
          {renderModelField(m.cli, m.model, (model) => updateMember(idx, { model }))}
          <button
            className="ms-remove"
            onClick={() => removeMember(idx)}
            disabled={council.members.length <= 1}
            title="Remove member"
          >
            −
          </button>
        </div>
      ))}
      <button className="ms-add" onClick={addMember}>
        + Add member
      </button>

      <div className="ms-section-label">Chairman (final synthesis)</div>
      <div className="ms-row">
        {cliSelect(council.chairman.cli, (cli) => updateChairman({ cli, model: null }))}
        {renderModelField(council.chairman.cli, council.chairman.model, (model) =>
          updateChairman({ model })
        )}
      </div>

      <div className="ms-status">
        {CLI_OPTIONS.map((o) => (
          <span key={o.id} className={`status-pill ${status[o.id]?.available ? 'ok' : 'off'}`}>
            {status[o.id]?.available ? '✅' : '❌'} {o.label}
            {status[o.id]?.default_model ? (
              <em className="pill-model"> · {status[o.id].default_model}</em>
            ) : null}
          </span>
        ))}
      </div>
    </div>
  );
}
