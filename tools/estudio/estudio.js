"use strict";

/* O Estúdio escreve UMA coisa: a dungeon. Cinco etapas, uma de cada vez —
   escolher, a dungeon, o chefe, o caminho, revisar e baixar —, e no fim um
   arquivo só, que é o mesmo que o bot vai receber pelo Discord.

   O rascunho é o próprio arquivo (`rascunho().pacote`): cada campo escreve
   direto nele, então não existe "aplicar" nem estado pela metade. O que
   vale para o jogo — a validação, a simulação, os limites, as listas — vem
   do servidor, que importa o bot. A página não tem regra própria. */

const $ = id => document.getElementById(id);
const copiar = valor => JSON.parse(JSON.stringify(valor));
const objeto = valor => valor !== null && typeof valor === "object" && !Array.isArray(valor);
const texto = valor => valor == null ? "" : String(valor);
const normalizar = valor => texto(valor).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const pct = taxa => taxa == null ? "—" : `${Math.round(taxa * 100)}%`;
const NS = "incursoes.estudio.v3.";
const ETAPAS = ["Escolher", "Dungeon", "Chefe", "Caminho", "Revisar"];
const TITULOS = {
  Escolher: "Escolha a dungeon", Dungeon: "A dungeon", Chefe: "O chefe",
  Caminho: "O caminho", Revisar: "Revisar e baixar",
};
const PROXIMO = {Dungeon: "Próximo: o chefe →", Chefe: "Próximo: o caminho →", Caminho: "Próximo: revisar →"};
// Lutas por tamanho de grupo. Pouco para virar veredito final, o bastante
// para o autor ajustar o bando sem esperar meio minuto a cada tentativa.
const REPETICOES = 240;

let C;                        // /api/conteudo
let rascunhos = {};           // chave -> rascunho
let chave = null;             // o rascunho aberto
let etapa = "Escolher";
let abaPrevia = "anuncio";
let linhasChefe = null, linhasDe = null;
let simulando = false, relogio = null;
let armazenamentoFalhou = false, timerToast, pedidoConferir = 0, pedidoCaminho = 0;
const BESTIARIO = new Set();

/* -------------------------------------------------------------- miúdos */

function no(tag, classe, conteudo) {
  const n = document.createElement(tag);
  if (classe) n.className = classe;
  if (conteudo != null) n.textContent = texto(conteudo);
  return n;
}
function aviso(mensagem) {
  clearTimeout(timerToast);
  $("toast").textContent = mensagem;
  $("toast").hidden = false;
  timerToast = setTimeout(() => { $("toast").hidden = true; }, 4000);
}
async function api(url, dados) {
  const resposta = await fetch(url, dados === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(dados),
  });
  const r = await resposta.json();
  if (!resposta.ok) throw new Error(r.erro || `Falha ao consultar o estúdio (${resposta.status}).`);
  return r;
}
function recados(id, r, sucesso = "Nenhum problema encontrado.") {
  const caixa = $(id);
  caixa.replaceChildren();
  const problemas = r.problemas || [], avisos = r.avisos || [];
  caixa.className = caixa.className.replace(/\b(erro|aviso|ok)\b/g, "").trim()
    + " " + (r.erro || problemas.length ? "erro" : avisos.length ? "aviso" : "ok");
  caixa.hidden = false;
  caixa.append(no("strong", "", r.erro || (problemas.length
    ? `${problemas.length} problema(s) — o bot recusa a dungeon assim`
    : avisos.length ? `${avisos.length} aviso(s) — o bot aceita, mas vale olhar` : sucesso)));
  const mensagens = [...problemas, ...avisos];
  if (mensagens.length) {
    const lista = no("ul");
    mensagens.forEach(m => lista.append(no("li", "", m)));
    caixa.append(lista);
  }
}
function preencher(alvo, pares, escolhido) {
  alvo.replaceChildren();
  pares.forEach(([valor, rotulo]) => {
    const o = document.createElement("option");
    o.value = valor; o.textContent = rotulo;
    if (texto(valor) === texto(escolhido)) o.selected = true;
    alvo.append(o);
  });
}
function numero(id) {
  const bruto = $(id).value.trim();
  if (bruto === "") return null;
  const n = Number(bruto);
  return Number.isFinite(n) ? n : null;
}
function quando(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
}

/* ----------------------------------------------------------- rascunhos */

function rascunho() { return chave ? rascunhos[chave] : undefined; }
function inc() { return rascunho()?.pacote.incursao; }
function chefe() { return inc()?.objetivo; }

function lerLocal(nome) {
  try { return JSON.parse(localStorage.getItem(NS + nome)); } catch { return null; }
}
function gravarLocal(nome, valor) {
  try { localStorage.setItem(NS + nome, JSON.stringify(valor)); return true; }
  catch {
    if (!armazenamentoFalhou) aviso("Não foi possível guardar o rascunho neste navegador. Baixe o arquivo para não perder o trabalho.");
    armazenamentoFalhou = true;
    return false;
  }
}
function guardar() {
  if (!C) return;
  gravarLocal("rascunhos", rascunhos);
  if (chave) gravarLocal("ultimo", chave);
  $("estado").textContent = armazenamentoFalhou
    ? "Baixe o arquivo para não perder o trabalho" : "Rascunho salvo neste navegador";
  $("estado").classList.toggle("falhou", armazenamentoFalhou);
}
/* Rascunho que não tem a forma de um rascunho não abre: um navegador com
   lixo de outra versão não pode quebrar a página na cara do autor. */
function rascunhoValido(r) {
  return objeto(r) && objeto(r.pacote) && objeto(r.pacote.incursao) && objeto(r.pacote.incursao.objetivo);
}
function carregarRascunhos() {
  const salvos = lerLocal("rascunhos");
  rascunhos = {};
  if (objeto(salvos)) Object.entries(salvos).forEach(([k, r]) => { if (rascunhoValido(r)) rascunhos[k] = r; });
}
function novoRascunho(incursao, base = null, idFixo = false, salas = []) {
  const agora = new Date().toISOString();
  return {
    pacote: {
      formato: C.formato.nome, versao: C.formato.versao,
      organizacao: texto(incursao.organizacao), incursao, salas,
    },
    base, idFixo, medida: null, criado: agora, atualizado: agora,
  };
}
function abrirRascunho(k, destino = "Dungeon") {
  chave = k;
  linhasChefe = null; linhasDe = null;
  guardar();
  irPara(destino);
}
function alterado() {
  const r = rascunho();
  if (!r) return;
  r.atualizado = new Date().toISOString();
  r.pacote.organizacao = texto(inc().organizacao);
  guardar();
  $("nomeAberto").textContent = rotuloAberto();
}

/* ------------------------------------------------------- o código (id)

   O autor não escreve o código: ele sai do nome. Enquanto a dungeon nunca
   foi baixada, o código acompanha o nome; depois do primeiro download ele
   fica, porque é por ele que o bot reconhece o reenvio como a MESMA
   dungeon — renomear não pode virar uma dungeon nova. */

function slug(nome) {
  return normalizar(nome).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48).replace(/_+$/, "");
}
function codigoLivre(base) {
  if (!base) return "";
  const ocupados = new Set(Object.keys(C.incursoes));
  let id = base, n = 2;
  while (ocupados.has(id)) id = `${base}_${n++}`;
  return id;
}
function acompanharNome() {
  if (!rascunho().idFixo) inc().id = codigoLivre(slug(inc().nome));
}

/* O chefe é um bando só: a dungeon tem um tier, então criatura por tier ou
   por tema no chefe é peso morto. Uma dungeon antiga que tenha escrito assim
   abre com o bando do tier dela, pela mesma queda que o bot usa. */
function bandoDoTier(porTier, tier) {
  const tiers = Object.keys(porTier || {}).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
  if (!tiers.length) return [];
  const abaixo = tiers.filter(t => t <= (tier || 0));
  return porTier[String(abaixo.length ? abaixo[abaixo.length - 1] : tiers[0])] || [];
}
function normalizarChefe(i) {
  if (!objeto(i.objetivo)) i.objetivo = {};
  const o = i.objetivo;
  o.id ||= "OBJ"; o.tipo = "Combate";
  o.nome = texto(o.nome); o.descricao = texto(o.descricao);
  if (!Array.isArray(o.monstros) || !o.monstros.length) {
    o.monstros = copiar(bandoDoTier(o.monstros_por_tier, i.tier));
  }
  delete o.monstros_por_tier; delete o.monstros_por_tema;
}

function incursaoEmBranco() {
  return {
    id: "", nome: "", organizacao: "", tamanho: "Média", tier: null,
    lore_inicial: "", lore_final: "", recompensa_mes: 10, pontos_conclusao: 10, imagem_capa: null,
    objetivo: {id: "OBJ", nome: "", tipo: "Combate", descricao: "", monstros: []},
  };
}
function criarNova() {
  const k = `r${Date.now()}`;
  rascunhos[k] = novoRascunho(incursaoEmBranco());
  abrirRascunho(k);
  $("dNome").focus();
}
function partirDe(id) {
  const original = C.incursoes[id];
  if (!original) return;
  const i = copiar(original);
  i.nome = `${texto(original.nome)} (cópia)`;
  normalizarChefe(i);
  const k = `r${Date.now()}`;
  rascunhos[k] = novoRascunho(i, {rotulo: `a original, “${texto(original.nome)}”`, incursao: copiar(original)});
  chave = k;
  acompanharNome();
  abrirRascunho(k);
  aviso(`Cópia de “${texto(original.nome)}” aberta. A original não muda.`);
}
/* Abrir um arquivo baixado antes continua o trabalho de onde parou. O
   código dele fica fixo: é o arquivo que já pode ter sido enviado. */
async function abrirArquivo(evento) {
  const entrada = evento.target.files[0];
  evento.target.value = "";
  if (!entrada || !C) return;
  try {
    const dados = JSON.parse(await entrada.text());
    let pacote;
    // Uma incursão comum (de data/incursoes) também abre, mas como cópia: o
    // código dela é de outra dungeon, e não pode ficar travado no rascunho.
    const doEstudio = objeto(dados) && dados.formato === C.formato.nome;
    if (doEstudio) pacote = dados;
    else if (objeto(dados) && objeto(dados.objetivo)) pacote = {incursao: dados, salas: []};
    else throw new Error("este arquivo não é uma dungeon do Estúdio.");
    if (!objeto(pacote.incursao)) throw new Error("este arquivo não traz uma dungeon.");
    const i = pacote.incursao;
    normalizarChefe(i);
    if (!doEstudio) i.id = codigoLivre(slug(i.nome));
    const novo = novoRascunho(i, {rotulo: `o arquivo ${entrada.name}`, incursao: copiar(i)}, doEstudio,
      Array.isArray(pacote.salas) ? pacote.salas : []);
    const mesmo = Object.keys(rascunhos).find(k => rascunhos[k].idFixo && i.id && rascunhos[k].pacote.incursao.id === i.id);
    let k = `r${Date.now()}`;
    if (mesmo && confirm(`Você já tem um rascunho de “${texto(rascunhos[mesmo].pacote.incursao.nome)}”. Trocar o rascunho pelo arquivo?`)) k = mesmo;
    rascunhos[k] = novo;
    abrirRascunho(k);
    aviso(`“${texto(i.nome) || entrada.name}” aberta.`);
  } catch (erro) { aviso(`Não foi possível abrir: ${erro.message}`); }
}

/* ------------------------------------------------------------- etapas */

function rotuloAberto() {
  const i = inc();
  if (!i || etapa === "Escolher") return "";
  return [texto(i.nome) || "Dungeon sem nome", texto(i.organizacao)].filter(Boolean).join(" · ");
}
function irPara(nome, foco = true) {
  if (nome !== "Escolher" && !rascunho()) return;
  etapa = nome;
  document.body.dataset.etapa = nome;
  ETAPAS.forEach(e => { $("etapa" + e).hidden = e !== nome; });
  document.querySelectorAll(".passos [data-etapa]").forEach(b => {
    b.disabled = b.dataset.etapa !== "Escolher" && !rascunho();
    if (b.dataset.etapa === nome) b.setAttribute("aria-current", "step");
    else b.removeAttribute("aria-current");
  });
  $("tituloEtapa").textContent = TITULOS[nome];
  $("nomeAberto").textContent = rotuloAberto();
  $("btVoltar").hidden = nome === "Escolher";
  $("btVoltar").textContent = nome === "Dungeon" ? "← Suas dungeons" : "← Voltar";
  $("btProximo").hidden = !PROXIMO[nome];
  $("btProximo").textContent = PROXIMO[nome] || "";
  if (nome === "Escolher") desenharEscolher();
  if (nome === "Dungeon") mostrarDungeon();
  if (nome === "Chefe") mostrarChefe();
  if (nome === "Caminho") mostrarCaminho();
  if (nome === "Revisar") mostrarRevisao();
  window.scrollTo(0, 0);
  if (foco) $("tituloEtapa").focus({preventScroll: true});
}
function passo(delta) {
  const i = ETAPAS.indexOf(etapa) + delta;
  if (i >= 0 && i < ETAPAS.length) irPara(ETAPAS[i]);
}

/* ------------------------------------------------------- 1. escolher */

function resumoCurto(i, comOrganizacao = true) {
  const partes = comOrganizacao ? [texto(i.organizacao) || "sem Organização"] : [];
  partes.push(i.tier ? `T${i.tier}` : "sem tier");
  if (i.tamanho) partes.push(i.tamanho);
  return partes.join(" · ");
}
function desenharEscolher() {
  const lista = $("listaRascunhos");
  lista.replaceChildren();
  const chaves = Object.keys(rascunhos).sort((a, b) => texto(rascunhos[b].atualizado).localeCompare(texto(rascunhos[a].atualizado)));
  chaves.forEach(k => {
    const r = rascunhos[k], i = r.pacote.incursao;
    const item = no("li", "cartao");
    const abrir = no("button", "cartao-abrir");
    abrir.type = "button";
    abrir.append(no("span", "cartao-nome", texto(i.nome) || "Dungeon sem nome"),
      no("span", "cartao-meta", resumoCurto(i)),
      no("span", "cartao-meta", `editada em ${quando(r.atualizado)}`));
    abrir.addEventListener("click", () => abrirRascunho(k));
    const apagar = no("button", "botao discreto pequena perigo", "Apagar");
    apagar.type = "button";
    apagar.setAttribute("aria-label", `Apagar o rascunho ${texto(i.nome) || "sem nome"}`);
    apagar.addEventListener("click", () => {
      if (!confirm(`Apagar o rascunho “${texto(i.nome) || "sem nome"}” deste navegador? Isso não tem volta — um arquivo que você já baixou continua no seu computador.`)) return;
      delete rascunhos[k];
      if (chave === k) chave = null;
      guardar(); irPara("Escolher", false);
    });
    item.append(abrir, apagar);
    lista.append(item);
  });
  $("semRascunhos").hidden = chaves.length > 0;

  const prontas = $("listaProntas");
  prontas.replaceChildren();
  C.organizacoes.forEach(org => {
    const daOrg = Object.entries(C.incursoes).filter(([, i]) => i.organizacao === org)
      .sort(([, a], [, b]) => (a.tier || 5) - (b.tier || 5) || texto(a.nome).localeCompare(texto(b.nome)));
    if (!daOrg.length) return;
    const grupo = no("div", "grupo-prontas");
    grupo.append(no("h4", "", org));
    const ul = no("ul", "cartoes compactos");
    daOrg.forEach(([id, i]) => {
      const li = no("li", "cartao");
      const b = no("button", "cartao-abrir");
      b.type = "button";
      b.append(no("span", "cartao-nome", texto(i.nome)), no("span", "cartao-meta", resumoCurto(i, false)));
      b.addEventListener("click", () => partirDe(id));
      li.append(b); ul.append(li);
    });
    grupo.append(ul); prontas.append(grupo);
  });
}

/* ------------------------------------------------------ 2. a dungeon */

function tierRotulo(t) {
  const n = Number(t);
  return n >= C.limites.tier_maximo
    ? `Tier ${n} · aberta a todos`
    : `Tier ${n} · até o nível ${C.nivel_maximo_do_tier[String(n)]}`;
}
function familiaDe(tipo) { return (C.tipos_de_sala.find(t => t.id === tipo) || {}).familia; }
function sorteaveisDe(org) {
  const b = C.bancos[org];
  return b ? b.salas.filter(s => familiaDe(s.tipo) !== "parada").length : 0;
}
function resumoDoCaminho(tamanho) {
  // O mesmo texto de `embeds.resumo_do_caminho`, que é o que o grupo lê.
  const t = C.tamanhos[tamanho];
  if (!t) return "";
  const descansos = t.paradas - t.salas;
  if (!descansos) return `${t.salas} salas até o objetivo, sem descanso`;
  const quais = {1: "um descanso", 2: "dois descansos"}[descansos] || `${descansos} descansos`;
  return `${t.salas} salas e ${quais} até o objetivo`;
}
function chamada(lore) {
  // O corte de `embeds.chamada`: o primeiro parágrafo, até o limite do bot.
  const primeiro = texto(lore).trim().split("\n\n")[0].trim();
  const limite = C.limites.chamada;
  if (primeiro.length <= limite) return primeiro;
  const corte = primeiro.slice(0, limite);
  const espaco = corte.lastIndexOf(" ");
  return (espaco > 0 ? corte.slice(0, espaco) : corte) + "…";
}
function tituloDoCartao(i) {
  // `embeds.titulo_da_incursao`: o tier anda colado no nome.
  const nome = texto(i.nome) || "Sua dungeon";
  if (!i.tier) return nome;
  return Number(i.tier) >= C.limites.tier_maximo ? `${nome} (tier livre)` : `${nome} (T${i.tier})`;
}

function mostrarDungeon() {
  const i = inc();
  $("dNome").value = texto(i.nome);
  preencher($("dOrg"), [["", "Escolha…"], ...C.organizacoes.map(o => [o, `${o} · ${sorteaveisDe(o)} salas`])], i.organizacao);
  preencher($("dTier"), [["", "Escolha…"], ...Array.from({length: C.limites.tier_maximo}, (_, n) => [String(n + 1), tierRotulo(n + 1)])], i.tier ?? "");
  preencher($("dTamanho"), Object.keys(C.tamanhos).map(t => {
    const {salas, paradas} = C.tamanhos[t], descansos = paradas - salas;
    return [t, `${t} · ${salas} salas${descansos ? ` + ${descansos} descanso${descansos > 1 ? "s" : ""}` : ""}`];
  }), i.tamanho || "Média");
  $("dLore").value = texto(i.lore_inicial);
  $("dLoreFinal").value = texto(i.lore_final);
  $("dRecompensa").value = i.recompensa_mes ?? "";
  $("dPontos").value = i.pontos_conclusao ?? "";
  $("dCapa").value = texto(i.imagem_capa);
  atualizarDungeon();
}
function contar(alvo, quantos, aviso, teto) {
  $(alvo).textContent = quantos;
  $(alvo).classList.toggle("invalido", quantos > teto);
  $(alvo).classList.toggle("atencao", quantos > aviso && quantos <= teto);
}
function atualizarDungeon() {
  const i = inc(), L = C.limites;
  contar("cNome", texto(i.nome).length, L.aviso_titulo, L.titulo);
  contar("cLore", texto(i.lore_inicial).length, L.aviso_lore, L.descricao);
  contar("cLoreFinal", texto(i.lore_final).length, L.aviso_lore, L.descricao);
  $("dCodigo").textContent = i.id
    ? `Código: ${i.id}${rascunho().idFixo ? " · fixo" : ""}` : "O código sai do nome.";
  $("dCodigo").title = rascunho().idFixo
    ? "Fixo desde o primeiro download: reenviar o arquivo atualiza a mesma dungeon, mesmo com outro nome."
    : "Acompanha o nome até o primeiro download.";

  // O que cada escolha muda no jogo, dito na hora em que se escolhe.
  const partes = [];
  if (i.tier) partes.push(Number(i.tier) >= L.tier_maximo
    ? "Qualquer personagem pode entrar."
    : `Entra quem for do tier ${i.tier} ou menor (até o nível ${C.nivel_maximo_do_tier[String(i.tier)]}). O chefe é simulado nesse tier.`);
  if (i.organizacao) partes.push(`As salas do caminho saem do banco de ${i.organizacao} (${sorteaveisDe(i.organizacao)} salas).`);
  if (C.tamanhos[i.tamanho]) partes.push(`O caminho tem ${resumoDoCaminho(i.tamanho)}.`);
  $("dicaDungeon").textContent = partes.join(" ");
  previaDungeon();
}
function campoDiscord(nome, valor, emLinha = true) {
  const n = no("div", emLinha ? "" : "inteiro");
  n.append(no("strong", "", nome), no("span", "", valor));
  return n;
}
/* A prévia imita os três cartões de `src/embeds.py`: `recrutamento`,
   `lore_abertura` e `lore_fecho`. Mudou um deles, muda aqui. */
function previaDungeon() {
  const i = inc(), caixa = $("previaDungeon");
  caixa.replaceChildren();
  document.querySelectorAll("[data-previa]").forEach(b => b.setAttribute("aria-selected", b.dataset.previa === abaPrevia));
  const campos = no("div", "discord-campos");
  let titulo = `🗺️ ${tituloDoCartao(i)}`, corpo = "", nota = "";
  if (abaPrevia === "anuncio") {
    corpo = chamada(i.lore_inicial);
    campos.append(campoDiscord("Organização", i.organizacao || "—"),
      campoDiscord("Caminho", i.tamanho || "—"),
      campoDiscord("Recompensa", `${i.recompensa_mes ?? 0} MEs`),
      campoDiscord("Quem pode entrar", !i.tier ? "—" : Number(i.tier) >= C.limites.tier_maximo
        ? "🎚️ Tier livre — qualquer personagem entra"
        : `🎚️ Tier ${i.tier} — entra quem for tier ${i.tier} ou menos`, false));
    nota = "O anúncio do recrutamento mostra só o primeiro parágrafo da lore.";
  } else if (abaPrevia === "abertura") {
    corpo = texto(i.lore_inicial);
    campos.append(campoDiscord("Organização", i.organizacao || "—"),
      campoDiscord("Caminho", `${i.tamanho || "—"} — ${resumoDoCaminho(i.tamanho)}`),
      campoDiscord("Grupo", "5 aventureiro(s)"));
    nota = "A lore inteira, quando a run começa.";
  } else {
    titulo = `📖 ${tituloDoCartao(i)} — epílogo`;
    corpo = texto(i.lore_final);
    nota = texto(i.lore_final).trim() ? "Lido quando o grupo vence o chefe." : "Sem epílogo, a vitória sai sem esse cartão.";
  }
  caixa.append(no("h3", "", titulo));
  caixa.append(no("p", corpo ? "" : "vazio-previa", corpo || "Escreva o texto à esquerda."));
  if (campos.children.length) caixa.append(campos);
  const capa = texto(i.imagem_capa).trim();
  if (abaPrevia !== "epilogo" && /^https?:\/\//.test(capa)) {
    const img = document.createElement("img");
    img.src = capa; img.alt = "Capa da dungeon"; img.className = "capa";
    img.addEventListener("error", () => { img.replaceWith(no("p", "legenda", "A imagem não abriu. Confira o endereço.")); });
    caixa.append(img);
  }
  $("notaPrevia").textContent = nota;
}
function campoDaDungeon(id, aplicar, evento = "input") {
  $(id).addEventListener(evento, () => {
    if (!inc()) return;
    aplicar(inc(), $(id).value);
    alterado(); atualizarDungeon();
  });
}
campoDaDungeon("dNome", (i, v) => { i.nome = v; acompanharNome(); });
campoDaDungeon("dOrg", (i, v) => { i.organizacao = v; }, "change");
campoDaDungeon("dTier", (i, v) => { i.tier = v ? Number(v) : null; }, "change");
campoDaDungeon("dTamanho", (i, v) => { i.tamanho = v; }, "change");
campoDaDungeon("dLore", (i, v) => { i.lore_inicial = v; });
campoDaDungeon("dLoreFinal", (i, v) => { i.lore_final = v; });
campoDaDungeon("dRecompensa", i => { i.recompensa_mes = numero("dRecompensa"); });
campoDaDungeon("dPontos", i => { i.pontos_conclusao = numero("dPontos"); });
campoDaDungeon("dCapa", (i, v) => { i.imagem_capa = v.trim() || null; });
document.querySelectorAll("[data-previa]").forEach(b => b.addEventListener("click", () => {
  abaPrevia = b.dataset.previa; previaDungeon();
}));

/* --------------------------------------------------------- 3. o chefe */

/* Uma criatura com números escritos à mão é "ficha própria": o bot usa os
   números dela, e não os do livro. Trocar o nome por um do bestiário troca
   a ficha pela do livro — senão o Behir sairia com os números do monstro
   que estava antes na linha. */
const temFicha = m => ["ca", "ataque", "hp", "dano"].some(c => m[c] != null && m[c] !== "");

function linhas() {
  if (linhasChefe === null || linhasDe !== chave) {
    linhasChefe = copiar(chefe().monstros || []).map(m => ({...m}));
    linhasDe = chave;
  }
  return linhasChefe;
}
function gravarChefe() {
  chefe().monstros = linhas().filter(m => texto(m.nome).trim()).map(m => {
    const limpo = {...m, nome: texto(m.nome).trim()};
    const q = Number(limpo.quantidade);
    if (Number.isFinite(q) && q > 1) limpo.quantidade = q; else delete limpo.quantidade;
    return limpo;
  });
  alterado(); atualizarChefe();
}
function desenharCriaturas() {
  const corpo = $("linhasChefe");
  corpo.replaceChildren();
  const lista = linhas();
  lista.forEach((m, i) => {
    const tr = no("tr");
    const nome = no("td");
    const campo = document.createElement("input");
    campo.type = "text"; campo.value = texto(m.nome);
    campo.setAttribute("list", "listaCriaturas");
    campo.setAttribute("aria-label", `Criatura ${i + 1}`);
    campo.addEventListener("input", () => {
      const v = campo.value;
      if (temFicha(lista[i]) && BESTIARIO.has(v.trim())) {
        lista[i] = {nome: v, ...(lista[i].quantidade ? {quantidade: lista[i].quantidade} : {})};
        desenharCriaturas(); gravarChefe();
        $("linhasChefe").querySelectorAll('input[type="text"]')[i]?.focus();
        return;
      }
      lista[i].nome = v;
      gravarChefe();
    });
    nome.append(campo);
    if (temFicha(m)) {
      const marca = no("span", "ficha-propria", "ficha própria");
      marca.title = "Esta criatura tem números escritos no arquivo. Trocar para um nome do bestiário usa os números do livro.";
      nome.append(marca);
    }
    const quantas = no("td", "n");
    const q = document.createElement("input");
    q.type = "number"; q.min = "1"; q.max = String(C.limites.inimigos);
    q.value = String(m.quantidade || 1);
    q.setAttribute("aria-label", `Quantas de ${texto(m.nome) || "criatura " + (i + 1)}`);
    q.addEventListener("input", () => { lista[i].quantidade = Number(q.value) || 1; gravarChefe(); });
    quantas.append(q);
    const fora = no("td");
    const tirar = no("button", "botao discreto pequena", "×");
    tirar.type = "button"; tirar.setAttribute("aria-label", `Remover ${texto(m.nome) || "criatura"}`);
    tirar.addEventListener("click", () => { lista.splice(i, 1); desenharCriaturas(); gravarChefe(); });
    fora.append(tirar);
    tr.append(nome, quantas, fora);
    corpo.append(tr);
  });
}
function mostrarChefe() {
  const o = chefe();
  $("cSala").value = texto(o.nome);
  $("cDesc").value = texto(o.descricao);
  desenharCriaturas();
  atualizarChefe();
}
function totalDoBando() {
  return (chefe().monstros || []).reduce((soma, m) => soma + Math.max(1, Number(m.quantidade) || 1), 0);
}
function atualizarChefe() {
  const o = chefe(), L = C.limites;
  contar("cSalaConta", texto(o.nome).length, L.aviso_titulo, L.titulo);
  contar("cDescConta", texto(o.descricao).length, L.aviso_descricao, L.descricao);
  const total = totalDoBando(), teto = L.inimigos;
  const desconhecidas = (o.monstros || []).filter(m => !temFicha(m) && !BESTIARIO.has(texto(m.nome).trim()));
  const recado = $("recadoChefe");
  recado.textContent = !total ? "O chefe precisa de pelo menos uma criatura."
    : desconhecidas.length ? `Não estão no bestiário: ${desconhecidas.map(m => m.nome).join(", ")}. Escolha um nome da lista.`
    : `${total} criatura(s) no bando${total > teto ? ` — o máximo é ${teto}` : ` · máximo ${teto}`}.`;
  recado.classList.toggle("invalido", total > teto || desconhecidas.length > 0);
  atualizarSimulacao();
}
$("cSala").addEventListener("input", () => { if (!chefe()) return; chefe().nome = $("cSala").value; alterado(); atualizarChefe(); });
$("cDesc").addEventListener("input", () => { if (!chefe()) return; chefe().descricao = $("cDesc").value; alterado(); atualizarChefe(); });
$("btCriatura").addEventListener("click", () => {
  if (!chefe()) return;
  linhas().push({nome: "", quantidade: 1});
  desenharCriaturas();
  const campos = $("linhasChefe").querySelectorAll('input[type="text"]');
  campos[campos.length - 1]?.focus();
});

/* A simulação do chefe. O tier vem da dungeon, e não de um campo: o chefe
   é sempre lutado no tier dela, e um seletor aqui só serviria para medir
   a luta errada. O nível também não é campo — a ficha não muda dentro do
   tier, então qualquer nível do tier dá o mesmo combate. */
function assinatura() {
  return JSON.stringify([inc().tier, chefe().monstros, $("fSeis").checked, $("fSemente").value]);
}
function motivoParaNaoSimular() {
  if (C.falta_para_simular) return C.falta_para_simular;
  if (!inc().tier) return "Escolha o tier na etapa A dungeon: o chefe é simulado nele.";
  if (!totalDoBando()) return "Adicione pelo menos uma criatura ao chefe.";
  return "";
}
function atualizarSimulacao() {
  const i = inc(), motivo = motivoParaNaoSimular();
  $("quemSimula").textContent = i.tier
    ? `Grupos de 5 jogadores do tier ${i.tier}, contra as formações de referência do bot. Pode levar até meio minuto.`
    : "O grupo é simulado no tier da dungeon.";
  $("motivoSimular").textContent = motivo;
  $("motivoSimular").hidden = !motivo;
  $("btSimular").disabled = simulando || !!motivo;
  const m = rascunho()?.medida;
  $("medidaVelha").hidden = !m || m.assinatura === assinatura();
  desenharResultado();
}
async function simular() {
  if (simulando || motivoParaNaoSimular()) return;
  const k = chave, feita = assinatura(), o = chefe();
  // O bot exige nome e texto da sala; para medir o bando eles não importam,
  // e o autor não deveria ter de escrever a descrição antes de testar a luta.
  const sala = {...copiar(o), nome: texto(o.nome).trim() || "Chefe", descricao: texto(o.descricao).trim() || "—"};
  const pedido = {sala, tier: Number(inc().tier), grupos: $("fSeis").checked ? [5, 6] : [5], repeticoes: REPETICOES};
  if ($("fSemente").value !== "") pedido.semente = Number($("fSemente").value);
  simulando = true; $("saidaSim").hidden = true;
  const inicio = Date.now();
  const marcar = () => { $("btSimular").textContent = `Simulando… ${Math.round((Date.now() - inicio) / 1000)} s`; };
  marcar(); relogio = setInterval(marcar, 1000);
  atualizarSimulacao();
  try {
    const r = await api("/api/simular", pedido);
    if (r.erro) { recados("saidaSim", r); return; }
    if (!rascunhos[k]) return;
    rascunhos[k].medida = {assinatura: feita, resposta: r, quando: new Date().toISOString()};
    guardar();
    if (k === chave && feita !== assinatura()) aviso("O chefe mudou durante a simulação. Simule de novo.");
  } catch (erro) { recados("saidaSim", {erro: erro.message}); }
  finally {
    simulando = false; clearInterval(relogio);
    $("btSimular").textContent = "Simular o chefe";
    if (k === chave && etapa === "Chefe") atualizarSimulacao();
  }
}
/* A régua: as três faixas na reta de 0 a 100%, e onde a luta caiu. A
   porcentagem sozinha deixava o autor adivinhar se 62% era o que ele
   queria; as faixas vêm do servidor (`tools/simulacao/regua.py`). */
function escala(taxa) {
  const n = no("div", "escala");
  n.setAttribute("aria-hidden", "true");
  Object.entries(C.dificuldades_de_combate).forEach(([nome, [lo, hi]]) => {
    const faixa = no("span", `faixa faixa-${nome}`, C.rotulos_de_combate[nome] || nome);
    faixa.style.left = `${lo * 100}%`; faixa.style.width = `${(hi - lo) * 100}%`;
    n.append(faixa);
  });
  const marca = no("span", "marca");
  marca.style.left = `${Math.max(0, Math.min(100, taxa * 100))}%`;
  n.append(marca);
  return n;
}
function proximoPasso(m) {
  const faixas = Object.values(C.dificuldades_de_combate);
  const teto = Math.max(...faixas.map(f => f[1])), piso = Math.min(...faixas.map(f => f[0]));
  const dicas = [];
  if (m.taxa > teto) dicas.push("Quase nenhum grupo perde. Para endurecer: aumente a quantidade ou troque por uma criatura mais forte.");
  else if (m.taxa < piso) dicas.push("A maioria dos grupos perde. Para aliviar: tire uma criatura ou troque por uma mais fraca.");
  else if (!m.dificuldade) dicas.push("Caiu entre duas faixas. Um ajuste pequeno na quantidade costuma levar para uma delas.");
  else dicas.push(`Dentro da faixa ${m.rotulo}.`);
  if (m.dizima && m.pior) dicas.push(`Atenção: uma das formações de referência vence só ${pct(m.pior.taxa)} das vezes. A média esconde isso — veja qual é em “Ver as formações”.`);
  return dicas;
}
function desenharResultado() {
  const caixa = $("resultado"), m = rascunho()?.medida;
  caixa.replaceChildren();
  if (!m) {
    caixa.className = "resultado-vazio";
    caixa.textContent = "Simule para ver quantas vezes o grupo vence.";
    return;
  }
  caixa.className = "resultado" + (m.assinatura === assinatura() ? "" : " velho");
  const r = m.resposta;
  r.medidas.forEach(med => {
    const bloco = no("div", "medida-grupo");
    const topo = no("div", "medida-topo");
    topo.append(no("b", "taxa-grande", pct(med.taxa)),
      no("span", "", `de vitórias com ${med.grupo} jogadores`),
      no("span", `veredito${med.dificuldade ? "" : " sem-faixa"}`, med.rotulo || ""));
    bloco.append(topo, escala(med.taxa));
    proximoPasso(med).forEach(d => bloco.append(no("p", "dica", d)));
    if (med.pior && pct(med.pior.taxa) === pct(med.melhor.taxa)) {
      bloco.append(no("p", "legenda", `Todas as formações de referência vencem ${pct(med.pior.taxa)}.`));
    } else if (med.pior) {
      bloco.append(no("p", "legenda", `A formação que mais sofre vence ${pct(med.pior.taxa)} (${med.pior.classes.join(", ")}), em ${med.pior.amostras} lutas. A que menos sofre, ${pct(med.melhor.taxa)}.`));
    }
    caixa.append(bloco);
  });
  const formacoes = no("details", "formacoes");
  formacoes.append(no("summary", "", "Ver as formações"));
  r.medidas.forEach(med => [...(med.composicoes || [])].sort((a, b) => a.taxa - b.taxa).forEach(c => {
    formacoes.append(no("p", "", `${med.grupo} jogadores · ${pct(c.taxa)} · ${c.classes.join(", ")}`));
  }));
  caixa.append(formacoes);
  const primeira = r.medidas[0] || {};
  caixa.append(no("p", "legenda meta",
    `${primeira.lutas ?? r.repeticoes} lutas · ${primeira.rodadas == null ? "—" : primeira.rodadas.toFixed(1)} rodadas em média · ${primeira.caidos?.toFixed(1) ?? "—"} caídos · semente ${r.semente}`));
}
$("btSimular").addEventListener("click", simular);
$("fSeis").addEventListener("change", atualizarSimulacao);
$("fSemente").addEventListener("input", atualizarSimulacao);

/* -------------------------------------------------------- 4. o caminho */

async function mostrarCaminho() {
  const i = inc(), id = ++pedidoCaminho;
  $("tabelaCaminho").replaceChildren();
  $("saidaCaminho").hidden = true;
  if (!i.organizacao) {
    $("contaCaminho").textContent = "Escolha a Organização na etapa A dungeon.";
    $("notaCaminho").textContent = "As salas do caminho saem do banco dela.";
    return;
  }
  $("contaCaminho").textContent = "Conferindo as salas…";
  try {
    const r = await api("/api/pool", {organizacao: i.organizacao, tamanho: i.tamanho || "Média", filtro: i.filtro || {}});
    if (id !== pedidoCaminho) return;
    if (r.erro) { recados("saidaCaminho", r); $("contaCaminho").textContent = "Não foi possível conferir."; return; }
    $("contaCaminho").textContent = `${r.pool.length} salas podem cair no caminho`;
    $("notaCaminho").textContent = `Uma ${i.tamanho || "Média"} atravessa ${r.terminar} salas; com ${r.folga} ou mais, toda parada oferece ${C.limites.opcoes_por_passo} portas.`
      + (i.filtro ? " Esta dungeon tem um filtro de salas, herdado da original." : "");
    if (r.problemas.length || r.avisos.length) recados("saidaCaminho", r);
    $("tabelaCaminho").replaceChildren(...r.pool.map(s => {
      const tr = no("tr"), nome = no("td");
      nome.append(no("small", "", s.id), no("span", "", s.nome));
      tr.append(nome, no("td", "", s.tipo), no("td", "", s.temas.join(", ") || "—"));
      return tr;
    }));
  } catch (erro) {
    if (id === pedidoCaminho) { recados("saidaCaminho", {erro: erro.message}); $("contaCaminho").textContent = "Não foi possível conferir."; }
  }
}

/* ------------------------------------------------- 5. revisar e baixar */

/* O arquivo que sai: o mesmo formato que o bot lê. Campo opcional vazio
   sai do arquivo em vez de ir como "" — o arquivo fica legível para quem
   revisa, e o bot trata ausente e vazio igual. */
function arquivo() {
  const p = copiar(rascunho().pacote), i = p.incursao;
  if (!texto(i.lore_final).trim()) delete i.lore_final;
  if (!texto(i.imagem_capa).trim()) delete i.imagem_capa;
  return {
    formato: C.formato.nome, versao: C.formato.versao,
    organizacao: texto(i.organizacao), incursao: i, salas: Array.isArray(p.salas) ? p.salas : [],
  };
}
function nomeDoArquivo() { return `${inc().id || "dungeon"}.json`; }

async function conferir() {
  const id = ++pedidoConferir, k = chave;
  try {
    const r = await api("/api/conferir", {dados: arquivo()});
    if (id !== pedidoConferir || k !== chave) return;
    recados("saidaRevisar", r, "Pronta para enviar: o bot não encontrou nenhum problema.");
    const problemas = (r.problemas || []).length;
    $("btBaixar").textContent = problemas ? "↓ Baixar mesmo assim" : "↓ Baixar arquivo";
    $("notaArquivo").textContent = notaDoArquivo(problemas);
  } catch (erro) { if (id === pedidoConferir) recados("saidaRevisar", {erro: erro.message}); }
}
function notaDoArquivo(problemas) {
  const partes = [`${nomeDoArquivo()} — é este arquivo que se envia pelo Discord. Abrindo ele aqui de novo, você continua de onde parou.`];
  if (!rascunho().idFixo && inc().id) partes.push(`O código “${inc().id}” fica fixo a partir deste download: reenviar o arquivo atualiza a mesma dungeon, mesmo que o nome mude.`);
  if (problemas) partes.push("O bot recusa o arquivo enquanto houver problema.");
  return partes.join(" ");
}
function linhaDoResumo(rotulo, valor, irPara_) {
  const dt = no("dt", "", rotulo), dd = no("dd", "", valor);
  if (irPara_) {
    const b = no("button", "link", "mudar");
    b.type = "button";
    b.addEventListener("click", () => irPara(irPara_));
    dd.append(" ", b);
  }
  $("resumo").append(dt, dd);
}
function bandoEmTexto(monstros) {
  return (monstros || []).map(m => `${m.quantidade || 1}× ${texto(m.nome)}`).join(", ") || "nenhuma criatura";
}
function mostrarRevisao() {
  const i = inc(), o = chefe(), m = rascunho().medida;
  $("resumo").replaceChildren();
  linhaDoResumo("Dungeon", `${texto(i.nome) || "sem nome"}${i.id ? ` (${i.id})` : ""}`, "Dungeon");
  linhaDoResumo("Organização", i.organizacao || "não escolhida", "Dungeon");
  linhaDoResumo("Quem entra", i.tier ? tierRotulo(i.tier) : "tier não escolhido", "Dungeon");
  linhaDoResumo("Caminho", `${i.tamanho || "—"}: ${resumoDoCaminho(i.tamanho)}`, "Caminho");
  linhaDoResumo("Chefe", `${texto(o.nome) || "sala sem nome"} — ${bandoEmTexto(o.monstros)}`, "Chefe");
  const medida = m?.resposta?.medidas?.[0];
  linhaDoResumo("Simulação do chefe", !m ? "ainda não simulado"
    : m.assinatura !== assinatura() ? `desatualizada (${pct(medida?.taxa)} antes da última mudança)`
    : `${pct(medida?.taxa)} de vitórias com 5 jogadores · ${medida?.rotulo || ""}`, "Chefe");
  linhaDoResumo("Recompensa", `${i.recompensa_mes ?? 0} MEs por pessoa · ${i.pontos_conclusao ?? 10} pontos para a Organização`);
  linhaDoResumo("Textos", `abertura com ${texto(i.lore_inicial).length} caracteres · ${texto(i.lore_final).trim() ? `epílogo com ${texto(i.lore_final).length}` : "sem epílogo"}`, "Dungeon");
  mostrarMudancas();
  $("btBaixar").textContent = "↓ Baixar arquivo";
  $("notaArquivo").textContent = notaDoArquivo(0);
  $("saidaRevisar").hidden = false;
  $("saidaRevisar").className = "recados largo";
  $("saidaRevisar").textContent = "Conferindo com as regras do bot…";
  conferir();
}
/* O que mudou em relação ao ponto de partida — a original copiada ou o
   arquivo aberto. Texto longo diz que mudou e o tamanho, e não o texto
   inteiro: a revisão tem de caber em trinta segundos. */
const CAMPOS_DA_REVISAO = [
  ["Nome", i => i.nome, "curto"], ["Organização", i => i.organizacao, "curto"],
  ["Tier", i => i.tier, "curto"], ["Tamanho", i => i.tamanho, "curto"],
  ["Lore de abertura", i => i.lore_inicial, "longo"], ["Epílogo", i => i.lore_final, "longo"],
  ["Recompensa (MEs)", i => i.recompensa_mes, "curto"], ["Pontos", i => i.pontos_conclusao, "curto"],
  ["Imagem de capa", i => i.imagem_capa, "curto"],
  ["Nome da sala do chefe", i => i.objetivo?.nome, "curto"],
  ["Texto da sala do chefe", i => i.objetivo?.descricao, "longo"],
  ["Criaturas do chefe", i => bandoEmTexto(i.objetivo?.monstros), "curto"],
];
function mostrarMudancas() {
  const lista = $("mudancas"), base = rascunho().base;
  lista.replaceChildren();
  if (!base) {
    $("baseMudou").textContent = "";
    lista.append(no("li", "nada", "Dungeon nova: tudo neste arquivo é novo."));
    return;
  }
  $("baseMudou").textContent = `Comparado com ${base.rotulo}.`;
  const agora = inc(), antes = base.incursao;
  const iguais = (a, b) => texto(a ?? "").trim() === texto(b ?? "").trim();
  CAMPOS_DA_REVISAO.forEach(([rotulo, ler, jeito]) => {
    const a = ler(antes), b = ler(agora);
    if (iguais(a, b)) return;
    const li = no("li");
    li.append(no("strong", "", rotulo), " ");
    li.append(jeito === "longo"
      ? `reescrito (${texto(a).length} → ${texto(b).length} caracteres)`
      : `${texto(a) || "vazio"} → ${texto(b) || "vazio"}`);
    lista.append(li);
  });
  if (!lista.children.length) lista.append(no("li", "nada", "Nada mudou ainda."));
}
function baixar() {
  if (!rascunho()) return;
  const dados = arquivo();
  const url = URL.createObjectURL(new Blob([JSON.stringify(dados, null, 2) + "\n"], {type: "application/json"}));
  const link = no("a"); link.href = url; link.download = nomeDoArquivo();
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  const fixou = !rascunho().idFixo && inc().id;
  rascunho().idFixo = true;
  alterado();
  if (etapa === "Revisar") $("notaArquivo").textContent = notaDoArquivo(0);
  aviso(fixou ? `Arquivo baixado. O código “${inc().id}” agora é fixo.` : "Arquivo baixado.");
}
$("btBaixar").addEventListener("click", baixar);

/* ------------------------------------------------------------- início */

async function iniciar() {
  try {
    C = await api("/api/conteudo");
    (C.criaturas || []).forEach(nome => BESTIARIO.add(nome));
    const nomes = $("listaCriaturas");
    nomes.replaceChildren(...(C.criaturas || []).map(nome => { const o = document.createElement("option"); o.value = nome; return o; }));
    [["tNome", C.limites.titulo], ["tLore", C.limites.descricao], ["tLoreFinal", C.limites.descricao],
     ["tSala", C.limites.titulo], ["tDesc", C.limites.descricao]].forEach(([id, n]) => { $(id).textContent = n; });
    carregarRascunhos();
    irPara("Escolher", false);
    guardar();
    // Ligados só agora: antes do conteúdo, o clique não teria o que criar e
    // sumiria sem aviso.
    $("btNova").disabled = false; $("btAbrirArquivo").disabled = false;
    if (C.problemas.length) recados("erroInicial", {avisos: C.problemas});
  } catch (erro) {
    recados("erroInicial", {erro: erro.message});
    $("estado").textContent = "Não foi possível carregar";
  }
}

document.querySelectorAll(".passos [data-etapa]").forEach(b => b.addEventListener("click", () => irPara(b.dataset.etapa)));
$("btVoltar").addEventListener("click", () => passo(-1));
$("btProximo").addEventListener("click", () => passo(1));
$("btNova").addEventListener("click", () => { if (C) criarNova(); });
$("btAbrirArquivo").addEventListener("click", () => { if (C) $("fArquivo").click(); });
$("fArquivo").addEventListener("change", abrirArquivo);
document.addEventListener("keydown", evento => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "s") {
    evento.preventDefault();
    if (rascunho()) baixar();
  }
});
window.addEventListener("beforeunload", guardar);
iniciar();
