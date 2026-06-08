import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

// Default council line-up. `model: null` => the backend applies that CLI's
// smart, auto-updating default (see agents.resolve_default_model). No model
// versions are hardcoded on the frontend.
const DEFAULT_COUNCIL = {
  members: [
    { cli: 'claude', model: null },
    { cli: 'codex', model: null },
    { cli: 'gemini', model: null },
    { cli: 'agy', model: null },
  ],
  chairman: { cli: 'claude', model: null },
};

const COUNCIL_KEY = 'llm-council-lineup';

function loadCouncil() {
  try {
    const raw = localStorage.getItem(COUNCIL_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {
    console.error('Failed to read saved council:', e);
  }
  return DEFAULT_COUNCIL;
}

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [council, setCouncil] = useState(loadCouncil);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (currentConversationId) loadConversation(currentConversationId);
  }, [currentConversationId]);

  // Persist the council line-up whenever it changes.
  useEffect(() => {
    try {
      localStorage.setItem(COUNCIL_KEY, JSON.stringify(council));
    } catch (e) {
      console.error('Failed to save council:', e);
    }
  }, [council]);

  const loadConversations = async () => {
    try {
      setConversations(await api.listConversations());
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (id) => {
    try {
      setCurrentConversation(await api.getConversation(id));
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      setConversations([
        { id: newConv.id, created_at: newConv.created_at, title: newConv.title, message_count: 0 },
        ...conversations,
      ]);
      setCurrentConversationId(newConv.id);
      setCurrentConversation(newConv);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = (id) => setCurrentConversationId(id);

  const handleSendMessage = async (content, attachments = []) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add the user message (attachments shown via their data URLs).
      const userMessage = {
        role: 'user',
        content,
        attachments: attachments.map((a) => ({
          filename: a.filename,
          mime: a.mime,
          url: a.dataUrl,
        })),
      };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
      }));

      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        loading: { stage1: false, stage2: false, stage3: false },
      };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...prev.messages, assistantMessage],
      }));

      const requestAttachments = attachments.map((a) => ({
        filename: a.filename,
        mime: a.mime,
        data_base64: a.dataUrl,
      }));

      await api.sendMessageStream(
        currentConversationId,
        content,
        { attachments: requestAttachments, council },
        (eventType, event) => {
          switch (eventType) {
            case 'stage1_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                messages[messages.length - 1].loading.stage1 = true;
                return { ...prev, messages };
              });
              break;
            case 'stage1_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const last = messages[messages.length - 1];
                last.stage1 = event.data;
                last.loading.stage1 = false;
                return { ...prev, messages };
              });
              break;
            case 'stage2_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                messages[messages.length - 1].loading.stage2 = true;
                return { ...prev, messages };
              });
              break;
            case 'stage2_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const last = messages[messages.length - 1];
                last.stage2 = event.data;
                last.metadata = event.metadata;
                last.loading.stage2 = false;
                return { ...prev, messages };
              });
              break;
            case 'stage3_start':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                messages[messages.length - 1].loading.stage3 = true;
                return { ...prev, messages };
              });
              break;
            case 'stage3_complete':
              setCurrentConversation((prev) => {
                const messages = [...prev.messages];
                const last = messages[messages.length - 1];
                last.stage3 = event.data;
                last.loading.stage3 = false;
                return { ...prev, messages };
              });
              break;
            case 'title_complete':
              loadConversations();
              break;
            case 'complete':
              loadConversations();
              setIsLoading(false);
              break;
            case 'error':
              console.error('Stream error:', event.message);
              setIsLoading(false);
              break;
            default:
              console.log('Unknown event type:', eventType);
          }
        }
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
      />
      <ChatInterface
        conversation={currentConversation}
        onSendMessage={handleSendMessage}
        isLoading={isLoading}
        council={council}
        onCouncilChange={setCouncil}
      />
    </div>
  );
}

export default App;
