import { useState, useEffect, useRef } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import ImageUpload from './ImageUpload';
import './ChatInterface.css';

export default function ChatInterface({ conversation, onSendMessage, isLoading }) {
  const [input, setInput] = useState('');
  const [images, setImages] = useState([]);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  const scrollToBottom = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  // Handle paste events for clipboard images
  useEffect(() => {
    const handlePaste = async (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      const imageItems = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          imageItems.push(items[i]);
        }
      }

      if (imageItems.length > 0) {
        e.preventDefault();
        
        const newImages = [];
        for (const item of imageItems) {
          const file = item.getAsFile();
          if (file) {
            const base64 = await fileToBase64(file);
            newImages.push({
              data: base64,
              name: `pasted-image-${Date.now()}.${file.type.split('/')[1]}`,
              type: file.type
            });
          }
        }
        
        setImages(prev => [...prev, ...newImages]);
      }
    };

    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    if ((input.trim() || images.length > 0) && !isLoading) {
      onSendMessage(
        input,
        images.map((img) => img.data),
      );
      setInput('');
      setImages([]);
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className='chat-interface'>
        <div className='empty-state'>
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className='chat-interface'>
      <div className='messages-container' ref={messagesContainerRef}>
        {conversation.messages.length === 0 ? (
          <div className='empty-state'>
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className='message-group'>
              {msg.role === 'user' ? (
                <div className='user-message'>
                  <div className='message-label'>You</div>
                  <div className='message-content'>
                    {msg.images && msg.images.length > 0 && (
                      <div className='message-images'>
                        {msg.images.map((img, imgIdx) => (
                          <img key={imgIdx} src={img} alt='Uploaded' />
                        ))}
                      </div>
                    )}
                    <div className='markdown-content'>
                      <MarkdownRenderer>{msg.content}</MarkdownRenderer>
                    </div>
                  </div>
                </div>
              ) : (
                <div className='assistant-message'>
                  <div className='message-label'>LLM Council</div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className='stage-loading'>
                      <div className='spinner'></div>
                      <span>Running Stage 1: Collecting individual responses...</span>
                    </div>
                  )}
                  {msg.stage1 && <Stage1 responses={msg.stage1} />}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className='stage-loading'>
                      <div className='spinner'></div>
                      <span>Running Stage 2: Peer rankings...</span>
                    </div>
                  )}
                  {msg.stage2 && <Stage2 rankings={msg.stage2} labelToModel={msg.metadata?.label_to_model} aggregateRankings={msg.metadata?.aggregate_rankings} />}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className='stage-loading'>
                      <div className='spinner'></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className='loading-indicator'>
            <div className='spinner'></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form className='input-form' onSubmit={handleSubmit}>
          <ImageUpload images={images} onImagesChange={setImages} />
          <div>
            <textarea
              className='message-input'
              placeholder='Ask your question or paste images (Cmd+V)... (Shift+Enter for new line, Enter to send)'
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              rows={3}
            />
            <button type='submit' className='send-button' disabled={(!input.trim() && images.length === 0) || isLoading}>
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
