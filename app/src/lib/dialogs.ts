import { Alert, AlertButton, Platform } from 'react-native';

/**
 * Alert.alert that also works on web, where react-native-web silently no-ops
 * it (a real bug we hit: taps that did nothing). Same signature as
 * Alert.alert so call sites only change the name.
 */
export function showAlert(title: string, message?: string, buttons?: AlertButton[]): void {
  if (Platform.OS !== 'web') {
    Alert.alert(title, message, buttons);
    return;
  }
  const text = message ? `${title}\n\n${message}` : title;
  const actions = (buttons ?? []).filter((b) => b.style !== 'cancel');
  const cancel = (buttons ?? []).find((b) => b.style === 'cancel');
  if (actions.length === 0) {
    window.alert(text);
    (buttons ?? [])[0]?.onPress?.();
    return;
  }
  const primary = actions[actions.length - 1];
  if (window.confirm(`${text}\n\n[OK = ${primary.text ?? 'OK'}]`)) primary.onPress?.();
  else cancel?.onPress?.();
}
