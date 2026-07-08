import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';

import { api } from '../../lib/api';
import { useBaby } from '../../lib/hooks';
import { colors, fonts, radius, spacing } from '../../lib/theme';
import type { ChatMeta } from '../../lib/types';
import { Muted } from '../../components/ui';

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
  error?: boolean;
}

const QUICK_PROMPTS = [
  'Draft an update for our metabolic team covering the last 24 hours',
  'How are we tracking against the lysine target today?',
  'Compare yesterday to the day before',
  'Any spit-ups or vomiting in the last 3 days?',
];

export default function Ask() {
  const { baby } = useBaby();
  const qc = useQueryClient();
  const [chatId, setChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const listRef = useRef<FlatList>(null);

  const chatsQ = useQuery({ queryKey: ['chats'], queryFn: api.listChats });

  const newChat = () => {
    setChatId(null);
    setMessages([]);
    setShowHistory(false);
  };

  const openChat = async (meta: ChatMeta) => {
    try {
      const full = await api.getChat(meta.id);
      setChatId(full.id);
      setMessages(full.messages.map((m) => ({ role: m.role, content: m.content })));
      setShowHistory(false);
    } catch (e: any) {
      Alert.alert('Could not open chat', e.message);
    }
  };

  const removeChat = (meta: ChatMeta) => {
    Alert.alert(`Delete "${meta.title}"?`, 'This removes it for both parents.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteChat(meta.id);
          qc.invalidateQueries({ queryKey: ['chats'] });
          if (meta.id === chatId) newChat();
        },
      },
    ]);
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || !baby || busy) return;
    setMessages((cur) => [...cur, { role: 'user', content }]);
    setInput('');
    setBusy(true);
    try {
      const resp = chatId
        ? await api.sendChatMessage(chatId, content)
        : await api.createChat(baby.id, content);
      setChatId(resp.chat.id);
      setMessages(resp.chat.messages.map((m) => ({ role: m.role, content: m.content })));
      qc.invalidateQueries({ queryKey: ['chats'] });
    } catch (e: any) {
      setMessages((cur) => [
        ...cur,
        {
          role: 'assistant',
          content:
            e?.status === 503
              ? 'The assistant isn’t set up yet — an API key needs to be added to the backend.'
              : `Sorry, something went wrong (${e?.message ?? 'network error'}). Try again.`,
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  if (showHistory) {
    return (
      <View style={{ flex: 1, padding: spacing.lg }}>
        <View style={styles.historyHeader}>
          <Text style={styles.historyTitle}>Family chats</Text>
          <Pressable onPress={() => setShowHistory(false)}>
            <Text style={styles.headerBtn}>Close</Text>
          </Pressable>
        </View>
        <FlatList
          data={chatsQ.data ?? []}
          keyExtractor={(c) => c.id}
          refreshing={chatsQ.isRefetching}
          onRefresh={() => chatsQ.refetch()}
          ListEmptyComponent={
            <Muted style={{ textAlign: 'center', marginTop: 30 }}>No chats yet.</Muted>
          }
          renderItem={({ item }) => (
            <Pressable
              style={styles.historyRow}
              onPress={() => openChat(item)}
              onLongPress={() => removeChat(item)}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.historyRowTitle} numberOfLines={1}>
                  {item.title}
                </Text>
                <Muted>
                  {item.created_by} · {new Date(item.updated_at).toLocaleString([], {
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                  })}
                </Muted>
              </View>
              <Text style={{ color: colors.muted, fontSize: 18 }}>›</Text>
            </Pressable>
          )}
        />
        <Muted style={{ textAlign: 'center' }}>Long-press a chat to delete it.</Muted>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}
    >
      <View style={styles.topBar}>
        <Pressable onPress={() => setShowHistory(true)}>
          <Text style={styles.headerBtn}>🕘 History</Text>
        </Pressable>
        <Pressable onPress={newChat}>
          <Text style={styles.headerBtn}>＋ New chat</Text>
        </Pressable>
      </View>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.md, flexGrow: 1 }}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <View style={{ flex: 1, justifyContent: 'center' }}>
            <Text style={styles.emptyTitle}>Ask about {baby?.name ?? 'your baby'}’s logs</Text>
            <Muted style={{ textAlign: 'center', marginBottom: spacing.lg }}>
              Answers use only your logged data — chats are shared with your partner.
            </Muted>
            {QUICK_PROMPTS.map((p) => (
              <Pressable key={p} style={styles.promptChip} onPress={() => send(p)}>
                <Text style={styles.promptText}>{p}</Text>
              </Pressable>
            ))}
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            onLongPress={() => Clipboard.setStringAsync(item.content)}
            style={[
              styles.bubble,
              item.role === 'user' ? styles.userBubble : styles.assistantBubble,
              item.error && styles.errorBubble,
            ]}
          >
            <Text style={item.role === 'user' ? styles.userText : styles.assistantText}>
              {item.content}
            </Text>
          </Pressable>
        )}
        ListFooterComponent={
          busy ? (
            <View style={[styles.bubble, styles.assistantBubble]}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : null
        }
      />
      <Muted style={{ textAlign: 'center', paddingHorizontal: spacing.lg }}>
        AI can make mistakes — verify before acting. Not medical advice.
      </Muted>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          placeholder="Ask anything about the logs…"
          placeholderTextColor={colors.muted}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={() => send(input)}
          returnKeyType="send"
          multiline
        />
        <Pressable
          style={[styles.sendBtn, (!input.trim() || busy) && { opacity: 0.4 }]}
          disabled={!input.trim() || busy}
          onPress={() => send(input)}
        >
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  headerBtn: { color: colors.primary, fontFamily: fonts.bold, fontSize: 15 },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  historyTitle: { fontSize: 18, fontFamily: fonts.heavy, color: colors.text },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  historyRowTitle: { fontFamily: fonts.bold, color: colors.text, fontSize: 15 },
  emptyTitle: {
    fontSize: 18,
    fontFamily: fonts.heavy,
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
  promptChip: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  promptText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 14 },
  bubble: {
    maxWidth: '85%',
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  userBubble: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  errorBubble: { borderColor: colors.danger },
  userText: { color: '#fff', fontSize: 15, lineHeight: 21, fontFamily: fonts.regular },
  assistantText: { color: colors.text, fontSize: 15, lineHeight: 21, fontFamily: fonts.regular },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: spacing.md,
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 15,
    maxHeight: 120,
    color: colors.text,
    fontFamily: fonts.regular,
  },
  sendBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendText: { color: '#fff', fontSize: 20, fontFamily: fonts.heavy },
});
