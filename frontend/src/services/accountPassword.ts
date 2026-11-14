/** New registration policy; existing credentials keep their login compatibility. */
export function accountPasswordError(password: string, registering: boolean): string | null {
  const length = Array.from(password).length;
  if (registering) {
    if (length < 8 || length > 24) return '密码请使用 8—24 个字符。';
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) return '密码必须同时包含英文字母和数字，可以包含符号。';
  } else if (length < 1 || length > 128) {
    return '请输入注册时设置的密码。';
  }
  return null;
}
