export function setLocalStorageItem(key, value, ttlInMs) {
  const now = new Date();
  const item = {
    value: value,
    expiry: ttlInMs ? now.getTime() + ttlInMs : null,
  };
  localStorage.setItem(key, JSON.stringify(item));
}


export function getLocalStorageItem(key) {
  const itemStr = localStorage.getItem(key);
  if (!itemStr) {
    return null;
  }
  let item;
  try {
    item = JSON.parse(itemStr);
  } catch {
    localStorage.removeItem(key);
    return null;
  }
  if (!item || typeof item !== "object") {
    localStorage.removeItem(key);
    return null;
  }
  const now = new Date();
  if (item.expiry != null && now.getTime() > Number(item.expiry)) {
    localStorage.removeItem(key);
    return null;
  }
  return item.value;
}
