import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import ModelSelector from './ModelSelector';
import { attachmentUrl } from '../api';
import './ChatInterface.css';

const ACCEPTED = ['image/', 'application/pdf'];

function isAccepted(file) {
  return ACCEPTED.some((p) => (file.type || '').startsWith(p));
}

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function isImage(mime) {
  return (mime || '').startsWith('image/');
}

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
  council,
  onCouncilChange,
}) {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState([]); // {filename, mime, dataUrl}
  const [showSettings, setShowSettings] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const addFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter(isAccepted);
    const read = await Promise.all(
      files.map(async (f) => ({
        filename: f.name || 'pasted-image.png',
        mime: f.type || 'application/octet-stream',
        dataUrl: await readFileAsDataURL(f),
      }))
    );
    if (read.length) setAttachments((prev) => [...prev, ...read]);
  };

  const handlePaste = (e) => {
    const items = e.clipboardData?.items || [];
    const files = [];
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file && isAccepted(file)) files.push(file);
      }
    }
    if (files.length) {
      e.preventDefault(); // don't paste the image as garbage text
      addFiles(files);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  const removeAttachment = (idx) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if ((input.trim() || attachments.length) && !isLoading) {
      onSendMessage(input, attachments);
      setInput('');
      setAttachments([]);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  const renderAttachments = (atts) => (
    <div className="msg-attachments">
      {atts.map((a, i) =>
        isImage(a.mime) ? (
          <a key={i} href={attachmentUrl(a.url)} target="_blank" rel="noreferrer">
            <img className="msg-attachment-img" src={attachmentUrl(a.url)} alt={a.filename} />
          </a>
        ) : (
          <a
            key={i}
            className="msg-attachment-file"
            href={attachmentUrl(a.url)}
            target="_blank"
            rel="noreferrer"
          >
            📄 {a.filename}
          </a>
        )
      )}
    </div>
  );

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="chat-title">{conversation.title || 'Conversation'}</div>
        <button
          className={`settings-toggle ${showSettings ? 'active' : ''}`}
          onClick={() => setShowSettings((s) => !s)}
          title="Configure council members & models"
        >
          ⚙ Council
        </button>
      </div>

      {showSettings && (
        <ModelSelector
          council={council}
          onChange={onCouncilChange}
          onClose={() => setShowSettings(false)}
        />
      )}

      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    {msg.attachments?.length > 0 && renderAttachments(msg.attachments)}
                    <div className="markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">LLM Council</div>

                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 2: Peer rankings...</span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                    />
                  )}

                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}
                </div>
              )}
            </div>
          ))
        )}

        <div ref={messagesEndRef} />
      </div>

      <form
        className={`input-form ${dragOver ? 'drag-over' : ''}`}
        onSubmit={handleSubmit}
        onDrop={handleDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
      >
        {attachments.length > 0 && (
          <div className="attachment-chips">
            {attachments.map((a, i) => (
              <div className="attachment-chip" key={i}>
                {isImage(a.mime) ? (
                  <img className="chip-thumb" src={a.dataUrl} alt={a.filename} />
                ) : (
                  <span className="chip-icon">📄</span>
                )}
                <span className="chip-name">{a.filename}</span>
                <button
                  type="button"
                  className="chip-remove"
                  onClick={() => removeAttachment(i)}
                  title="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="input-row">
          <button
            type="button"
            className="attach-button"
            onClick={() => fileInputRef.current?.click()}
            title="Attach image or PDF"
            disabled={isLoading}
          >
            📎
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            multiple
            style={{ display: 'none' }}
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = '';
            }}
          />
          <textarea
            className="message-input"
            placeholder="Ask your question... (paste or drop images/PDFs · Enter to send, Shift+Enter for newline)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={isLoading}
            rows={3}
          />
          <button
            type="submit"
            className="send-button"
            disabled={(!input.trim() && !attachments.length) || isLoading}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
