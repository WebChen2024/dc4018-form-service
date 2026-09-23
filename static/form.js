const empIdInput = document.getElementById('emp_id');
const lookupHint = document.getElementById('lookup_hint');
const fields = {
  name: document.getElementById('name'),
  dept: document.getElementById('dept'),
  phone: document.getElementById('phone'),
  email: document.getElementById('email'),
};

empIdInput.addEventListener('blur', async () => {
  const empId = empIdInput.value.trim();
  if (!empId) return;
  lookupHint.textContent = '查詢中...';
  try {
    const res = await fetch(`/lookup/${encodeURIComponent(empId)}`);
    const data = await res.json();
    if (data.found) {
      fields.name.value = data.name;
      fields.dept.value = data.dept;
      fields.phone.value = data.phone;
      fields.email.value = data.email;
      lookupHint.textContent = '已帶入上次填寫的識別資料，可自行修改。';
    } else {
      lookupHint.textContent = '查無這個員工編號的紀錄，請自行填寫（送出後會存起來，下次自動帶入）。';
    }
  } catch (e) {
    lookupHint.textContent = '';
  }
});

// 需求說明行數即時提示：粗略用換行數估計，跟伺服器端用全形字寬度算的行數不完全一樣，
// 只是提早提醒使用者注意，真正的頁數判斷仍以送出後伺服器回傳的結果為準。
const needInput = document.getElementById('need');
const needHint = document.getElementById('need_hint');
const needMaxLines = parseInt(needHint.dataset.maxLines || '8', 10);
const needHintDefault = needHint.textContent;

needInput.addEventListener('input', () => {
  const lines = needInput.value.split('\n').filter((l) => l.trim() !== '').length;
  if (lines > needMaxLines) {
    needHint.textContent = `目前約 ${lines} 行，可能超過 1 頁，建議精簡或改寫成簡短說明並註明「詳如附件」。`;
    needHint.classList.add('warn');
  } else {
    needHint.textContent = needHintDefault;
    needHint.classList.remove('warn');
  }
});
