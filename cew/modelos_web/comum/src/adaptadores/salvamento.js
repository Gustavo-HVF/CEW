// Salvamento no navegador (localStorage), versionado e validado; nunca derruba o jogo.
// Use JSON simples; para dados grandes troque por IndexedDB mantendo esta interface.
const PREFIXO = 'cew:';

export function salvar(chave, dados, versao = 1) {
  try {
    localStorage.setItem(PREFIXO + chave, JSON.stringify({ versao, salvo_em: Date.now(), dados }));
    return true;
  } catch (e) {
    console.warn('salvamento indisponivel:', e);
    return false;
  }
}

// validar(dados) -> true/false: recusa saves corrompidos ou de outra versao.
export function carregar(chave, versao = 1, validar = () => true) {
  try {
    const bruto = localStorage.getItem(PREFIXO + chave);
    if (!bruto) return null;
    const doc = JSON.parse(bruto);
    if (doc.versao !== versao || !validar(doc.dados)) return null;
    return doc.dados;
  } catch {
    return null;
  }
}

export function apagar(chave) {
  try { localStorage.removeItem(PREFIXO + chave); } catch { /* sem armazenamento */ }
}
