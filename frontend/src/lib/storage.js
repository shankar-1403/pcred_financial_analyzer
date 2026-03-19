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
  // if the item doesn't exist, return null
  if (!itemStr) {
    return null;
  }
  const item = JSON.parse(itemStr);
  const now = new Date();
  // compare the expiry time of the item with the current time
  if (item.expiry && now.getTime() > item.expiry) {
    // If the item is expired, delete the item from storage and return null
    localStorage.removeItem(key);
    return null;
  }
  return item.value;
}
