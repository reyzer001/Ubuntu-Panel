export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const PHONE_RE = /^\+?[0-9][0-9\s-]{5,19}$/;

export const isValidEmail = (v: string) => EMAIL_RE.test(v);
export const isValidPhone = (v: string) => PHONE_RE.test(v);
