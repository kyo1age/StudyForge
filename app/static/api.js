class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function message(data, status) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map(item => item.msg).join('; ');
  return `Сервер вернул ошибку HTTP ${status}.`;
}

export async function request(path, {method = 'GET', body} = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      signal: AbortSignal.timeout(20_000),
      headers: body ? {'Content-Type': 'application/json'} : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
  } catch {
    throw new ApiError('Сервер недоступен или не ответил вовремя. Проверьте соединение и попробуйте ещё раз.');
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(message(data, response.status), response.status);
  if (data === null) throw new ApiError('Сервер вернул неожиданный ответ.', response.status);
  return data;
}

// XMLHttpRequest reports actual upload bytes. All other API calls use Fetch.
export function uploadPdf(file, reportProgress, uploadId) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/documents');
    xhr.setRequestHeader('X-Upload-ID', uploadId);
    xhr.responseType = 'json';
    xhr.timeout = 240_000;
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) reportProgress(Math.round(event.loaded / event.total * 100));
    };
    xhr.onload = () => {
      if (xhr.status === 201 && xhr.response) resolve(xhr.response);
      else reject(new ApiError(message(xhr.response, xhr.status), xhr.status));
    };
    xhr.onerror = xhr.ontimeout = () => reject(new ApiError('Загрузка прервана. Проверьте соединение.'));
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

