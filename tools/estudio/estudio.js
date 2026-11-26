"use strict";

/* O Estúdio tem duas partes, separadas de propósito.

   A principal escreve a DUNGEON: cinco etapas, uma de cada vez — escolher, a
   dungeon, o chefe, o caminho, revisar e baixar —, e no fim um arquivo só,
   que é o que o bot vai receber pelo Discord.

   A outra escreve SALAS novas para o banco de uma Organização. Elas saem num
   arquivo próprio, enviado antes de qualquer dungeon que conte com elas: a
   sala não pertence a uma dungeon — ela cai em todas as da Organização cujo
   tema bata —, e a dungeon não carrega sala.

   Os rascunhos são os próprios arquivos: cada campo escreve direto no
   objeto, sem "aplicar" nem estado pela metade. O que vale para o jogo — a
   validação, a simulação, os limites, as listas — vem do servidor, que
   importa o bot. A página não tem regra própria. */

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
let rascunhos = {};           // chave -> rascunho de dungeon
let chave = null;             // a dungeon aberta
let etapa = "Escolher", parte = "Dungeons", abaPrevia = "anuncio";
let salasLocais = {};         // Organização -> salas novas do autor
let orgSalas = "", salaAberta = null, tierSala = 1;
const medidasSalas = {};      // "org|id" -> {tier: medida}; não vai para arquivo nenhum
let simulando = false;
let armazenamentoFalhou = false, timerToast, timerSalas;
let pedidoConferir = 0, pedidoCaminho = 0, pedidoSalas = 0;
// As linhas das tabelas de criatura, enquanto estão na tela — com as linhas
// em branco que o autor acabou de criar e que ainda não vão para o arquivo.
const linhasCache = new Map();
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
    ? `${problemas.length} problema(s) — o bot recusa assim`
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
function baixarJson(dados, nome) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(dados, null, 2) + "\n"], {type: "application/json"}));
  const link = no("a"); link.href = url; link.download = nome;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function fichas(alvo, lista, marcados, aoTrocar, contar) {
  const caixa = $(alvo);
  caixa.replaceChildren();
  lista.forEach(item => {
    const b = no("button", "ficha", item);
    b.type = "button";
    b.dataset.valor = item;
    if (contar) b.append(no("span", "quantas", contar(item)));
    b.setAttribute("aria-pressed", marcados.includes(item) ? "true" : "false");
    b.addEventListener("click", () => aoTrocar(item, !marcados.includes(item)));
    caixa.append(b);
  });
}

/* ----------------------------------------------------------- rascunhos */

function rascunho() { return chave ? rascunhos[chave] : undefined; }
function inc() { return rascunho()?.pacote.incursao; }
function chefe() { return inc()?.objetivo; }
function locais(org) {
  if (!Array.isArray(salasLocais[org])) salasLocais[org] = [];
  return salasLocais[org];
}

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
  gravarLocal("salas", salasLocais);
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
  const salas = lerLocal("salas");
  salasLocais = {};
  if (objeto(salas)) Object.entries(salas).forEach(([org, lista]) => {
    if (Array.isArray(lista)) salasLocais[org] = lista.filter(objeto);
  });
}
function novoRascunho(incursao, base = null, idFixo = false) {
  const agora = new Date().toISOString();
  return {
    pacote: {
      formato: C.formato.nome, versao: C.formato.versao,
      organizacao: texto(incursao.organizacao), incursao, salas: [],
    },
    base, idFixo, medida: null, medidasCaminho: {}, criado: agora, atualizado: agora,
  };
}
function abrirRascunho(k, destino = "Dungeon") {
  chave = k;
  linhasCache.clear();
  $("propostaChefe").replaceChildren();
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

/* A queda de tier do bot (`Sala.monstros_do_tier`): o tier exato; senão o
   maior escrito abaixo; senão o menor escrito. Aqui ela serve para AVISAR o
   autor e para abrir um chefe antigo — a conta do caminho vem do servidor. */
function tierEscritoPara(porTier, tier) {
  const tiers = Object.keys(porTier || {}).map(Number)
    .filter(n => Number.isFinite(n) && (porTier[String(n)] || []).length).sort((a, b) => a - b);
  if (!tiers.length) return null;
  const abaixo = tiers.filter(t => t <= (tier || 0));
  return abaixo.length ? abaixo[abaixo.length - 1] : tiers[0];
}
/* O chefe é um bando só: a dungeon tem um tier, então criatura por tier ou
   por tema no chefe é peso morto. Uma dungeon antiga que tenha escrito assim
   abre com o bando do tier dela, pela mesma queda que o bot usa. */
function normalizarChefe(i) {
  if (!objeto(i.objetivo)) i.objetivo = {};
  const o = i.objetivo;
  o.id ||= "OBJ"; o.tipo = "Combate";
  o.nome = texto(o.nome); o.descricao = texto(o.descricao);
  if (!Array.isArray(o.monstros) || !o.monstros.length) {
    const escrito = tierEscritoPara(o.monstros_por_tier, i.tier);
    o.monstros = escrito == null ? [] : copiar(o.monstros_por_tier[String(escrito)]);
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
    else if (objeto(dados) && objeto(dados.objetivo)) pacote = {incursao: dados};
    else throw new Error("este arquivo não é uma dungeon do Estúdio.");
    if (!objeto(pacote.incursao)) {
      throw new Error(Array.isArray(pacote.salas)
        ? "este arquivo só tem salas. Abra-o na parte Salas."
        : "este arquivo não traz uma dungeon.");
    }
    const i = pacote.incursao;
    normalizarChefe(i);
    if (!doEstudio) i.id = codigoLivre(slug(i.nome));
    const novo = novoRascunho(i, {rotulo: `o arquivo ${entrada.name}`, incursao: copiar(i)}, doEstudio);
    const mesmo = Object.keys(rascunhos).find(k => rascunhos[k].idFixo && i.id && rascunhos[k].pacote.incursao.id === i.id);
    let k = `r${Date.now()}`;
    if (mesmo && confirm(`Você já tem um rascunho de “${texto(rascunhos[mesmo].pacote.incursao.nome)}”. Trocar o rascunho pelo arquivo?`)) k = mesmo;
    rascunhos[k] = novo;
    abrirRascunho(k);
    aviso(`“${texto(i.nome) || entrada.name}” aberta.`);
  } catch (erro) { aviso(`Não foi possível abrir: ${erro.message}`); }
}

/* -------------------------------------------------------- as partes */

function irParte(nome) {
  parte = nome;
  document.body.dataset.parte = nome;
  $("parteDungeons").hidden = nome !== "Dungeons";
  $("parteSalas").hidden = nome !== "Salas";
  document.querySelectorAll(".partes [data-parte]").forEach(b => {
    if (b.dataset.parte === nome) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  if (nome === "Salas") mostrarParteSalas();
  else irPara(etapa, false);
}

/* ------------------------------------------------------------- etapas */

function rotuloAberto() {
  const i = inc();
  if (!i || etapa === "Escolher") return "";
  return [texto(i.nome) || "Dungeon sem nome", texto(i.organizacao)].filter(Boolean).join(" · ");
}
function irPara(nome, foco = true) {
  if (nome !== "Escolher" && !rascunho()) nome = "Escolher";
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
function salasDoBot(org) { return C.bancos[org]?.original?.salas || []; }
function sorteaveisDe(org) { return salasDoBot(org).filter(s => familiaDe(s.tipo) !== "parada").length; }
function rotuloDaOrganizacao(org) {
  const suas = locais(org).length;
  return `${org} · ${sorteaveisDe(org)} salas${suas ? ` + ${suas} suas` : ""}`;
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
  preencher($("dOrg"), [["", "Escolha…"], ...C.organizacoes.map(o => [o, rotuloDaOrganizacao(o)])], i.organizacao);
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

/* ---------------------------------------------- tabelas de criaturas

   A mesma tabela escreve o bando do chefe e os bandos por tier das salas.
   Uma criatura com números escritos à mão é "ficha própria": o bot usa os
   números dela, e não os do livro. Trocar o nome por um do bestiário troca
   a ficha pela do livro — senão o Behir sairia com os números do monstro
   que estava antes na linha. */

const temFicha = m => ["ca", "ataque", "hp", "dano"].some(c => m[c] != null && m[c] !== "");

function linhasDe(chaveLista, fonte) {
  if (!linhasCache.has(chaveLista)) linhasCache.set(chaveLista, copiar(fonte || []).map(m => ({...m})));
  return linhasCache.get(chaveLista);
}
function bandoDas(linhas) {
  return linhas.filter(m => texto(m.nome).trim()).map(m => {
    const limpo = {...m, nome: texto(m.nome).trim()};
    const q = Number(limpo.quantidade);
    if (Number.isFinite(q) && q > 1) limpo.quantidade = q; else delete limpo.quantidade;
    return limpo;
  });
}
function totalDe(monstros) {
  return (monstros || []).reduce((soma, m) => soma + Math.max(1, Number(m.quantidade) || 1), 0);
}
function recadoDoBando(monstros, vazio) {
  const total = totalDe(monstros), teto = C.limites.inimigos;
  const fora = (monstros || []).filter(m => !temFicha(m) && !BESTIARIO.has(texto(m.nome).trim()));
  if (!total) return [vazio, false];
  if (fora.length) return [`Não estão no bestiário: ${fora.map(m => m.nome).join(", ")}. Escolha um nome da lista.`, true];
  return [`${total} criatura(s) no bando${total > teto ? ` — o máximo é ${teto}` : ` · máximo ${teto}`}.`, total > teto];
}
function bandoEmTexto(monstros) {
  return (monstros || []).map(m => `${m.quantidade || 1}× ${texto(m.nome)}`).join(", ") || "nenhuma criatura";
}
function tabelaDeCriaturas(corpo, linhas, gravar) {
  corpo.replaceChildren();
  linhas.forEach((m, i) => {
    const tr = no("tr");
    const nome = no("td");
    const campo = document.createElement("input");
    campo.type = "text"; campo.value = texto(m.nome);
    campo.setAttribute("list", "listaCriaturas");
    campo.setAttribute("aria-label", `Criatura ${i + 1}`);
    campo.addEventListener("input", () => {
      const v = campo.value;
      if (temFicha(linhas[i]) && BESTIARIO.has(v.trim())) {
        linhas[i] = {nome: v, ...(linhas[i].quantidade ? {quantidade: linhas[i].quantidade} : {})};
        tabelaDeCriaturas(corpo, linhas, gravar); gravar();
        corpo.querySelectorAll('input[type="text"]')[i]?.focus();
        return;
      }
      linhas[i].nome = v;
      gravar();
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
    q.addEventListener("input", () => { linhas[i].quantidade = Number(q.value) || 1; gravar(); });
    quantas.append(q);
    const fora = no("td");
    const tirar = no("button", "botao discreto pequena", "×");
    tirar.type = "button"; tirar.setAttribute("aria-label", `Remover ${texto(m.nome) || "criatura"}`);
    tirar.addEventListener("click", () => { linhas.splice(i, 1); tabelaDeCriaturas(corpo, linhas, gravar); gravar(); });
    fora.append(tirar);
    tr.append(nome, quantas, fora);
    corpo.append(tr);
  });
}
function novaLinha(corpo, linhas, gravar) {
  linhas.push({nome: "", quantidade: 1});
  tabelaDeCriaturas(corpo, linhas, gravar);
  const campos = corpo.querySelectorAll('input[type="text"]');
  campos[campos.length - 1]?.focus();
}

/* ---------------------------------------------------------- simulação

   Uma simulação por vez na página: ela roda o motor do bot na máquina do
   autor, e duas juntas só deixariam as duas mais lentas. */

/* O andamento de verdade: a página dá um nome à medida e pergunta por ela
   enquanto espera. A barra conta formações ("3 de 7"), e o ajuste diz também
   em que medição está. Cancelar para na formação seguinte: a começada
   termina, e o que ela mediu é jogado fora. */
function novoPedido() { return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`; }
function montarAndamento(junto, pedido) {
  const caixa = no("div", "andamento");
  const barra = document.createElement("progress");
  barra.max = 1; barra.value = 0;
  barra.setAttribute("aria-label", "Andamento da simulação");
  const situacao = no("span", "legenda", "Começando…");
  const parar = no("button", "botao discreto pequena cancelar", "Cancelar");
  parar.type = "button";
  parar.addEventListener("click", async () => {
    parar.disabled = true; parar.textContent = "Cancelando…";
    try { await api("/api/cancelar", {pedido}); } catch { /* a medida acaba sozinha */ }
  });
  caixa.append(barra, situacao, parar);
  junto.after(caixa);
  const inicio = Date.now();
  return {
    atualizar(a) {
      if (!a || a.fim) return;
      barra.max = Math.max(1, a.total); barra.value = a.feitas;
      situacao.textContent = [
        a.fase,
        a.total ? `formação ${Math.min(a.feitas + 1, a.total)} de ${a.total}` : "",
        `${Math.round((Date.now() - inicio) / 1000)} s`,
      ].filter(Boolean).join(" · ");
    },
    remover() { caixa.remove(); },
  };
}
async function comAndamento(url, dados, junto) {
  const pedido = novoPedido(), andamento = montarAndamento(junto, pedido);
  const espiar = setInterval(async () => {
    try { andamento.atualizar(await api("/api/andamento", {pedido})); } catch { /* tenta de novo */ }
  }, 700);
  try { return await api(url, {...dados, pedido}); }
  finally { clearInterval(espiar); andamento.remover(); }
}
async function medir(sala, tier, botao, opcoes = {}) {
  if (simulando) return null;
  // O bot exige nome e texto da sala; para medir o bando eles não importam,
  // e o autor não deveria ter de escrever a descrição antes de testar a luta.
  const pedido = {
    sala: {...copiar(sala), nome: texto(sala.nome).trim() || "Sala", descricao: texto(sala.descricao).trim() || "—"},
    tier, grupos: opcoes.grupos || [5], repeticoes: REPETICOES,
  };
  if (opcoes.semente != null) pedido.semente = opcoes.semente;
  simulando = true;
  const rotulo = botao.textContent;
  botao.textContent = "Simulando…";
  atualizarBotoesDeSimular();
  try {
    const r = await comAndamento("/api/simular", pedido, botao);
    if (r?.cancelado) { aviso("Simulação cancelada."); return null; }
    return r;
  } finally {
    simulando = false;
    botao.textContent = rotulo;
    atualizarBotoesDeSimular();
  }
}

/* "Levar para": o autor escolhe a faixa, e o Estúdio acha a quantidade —
   sem trocar as criaturas, que ele escolheu pela ficção da sala. Só onde o
   bando pode mudar: o chefe e as salas novas. */
function botoesDeAjuste(med, aoAjustar) {
  const linha = no("div", "levar-para");
  linha.append(no("span", "legenda", "Levar para:"));
  Object.keys(C.dificuldades_de_combate).forEach(faixa => {
    const aqui = med.dificuldade === faixa, nome = C.rotulos_de_combate[faixa] || faixa;
    const b = no("button", "botao pequena ajustar", aqui ? `${nome} ✓` : nome);
    b.type = "button";
    b.dataset.faixa = faixa;
    b.dataset.aqui = aqui ? "1" : "";
    b.disabled = aqui || simulando || !!C.falta_para_simular;
    b.title = aqui ? "A luta já está nesta faixa." : `Procura quantas criaturas põem a luta em ${nome}.`;
    b.addEventListener("click", () => aoAjustar(faixa));
    linha.append(b);
  });
  return linha;
}
async function ajustarBando(bando, tier, alvo, caixa, aoUsar) {
  if (simulando || C.falta_para_simular) return;
  simulando = true;
  atualizarBotoesDeSimular();
  const nome = C.rotulos_de_combate[alvo] || alvo;
  const procurando = no("p", "legenda", `Procurando quantas criaturas põem a luta em ${nome}. Leva de meio minuto a uns dois.`);
  caixa.replaceChildren(procurando);
  try {
    const r = await comAndamento("/api/ajustar", {bando, tier, alvo, repeticoes: REPETICOES}, procurando);
    caixa.replaceChildren();
    if (r.cancelado) { aviso("Ajuste cancelado."); return; }
    if (r.erro) { caixa.append(no("p", "aviso-inline", r.erro)); return; }
    desenharProposta(caixa, r, aoUsar);
  } catch (erro) {
    caixa.replaceChildren(no("p", "aviso-inline", `Não foi possível ajustar: ${erro.message}`));
  } finally {
    simulando = false;
    atualizarBotoesDeSimular();
  }
}
function desenharProposta(caixa, r, aoUsar) {
  const med = r.medida.medidas[0] || {}, alvo = r.rotulo_do_alvo, nome = r.criatura;
  const frases = {
    serve: `Com ${r.quantidade}× ${nome} (em vez de ${r.antes}), a luta fica ${med.rotulo}.`,
    pula: `Nenhuma quantidade de ${nome} cai em ${alvo}: a faixa fica entre ${r.quantidade - 1} e ${r.quantidade}. `
      + `Com ${r.quantidade}, a luta fica ${med.rotulo}. Para acertar em cheio, troque parte do bando por uma criatura mais fraca.`,
    fraca: `Nem com ${r.quantidade}× ${nome}, o máximo que cabe no bando, a luta chega a ${alvo}. Troque por uma criatura mais forte.`,
    forte: `Mesmo com 1× ${nome}, a luta passa de ${alvo}. Troque por uma criatura mais fraca.`,
  };
  const bloco = no("div", "proposta");
  bloco.append(no("p", "", frases[r.veredito] || `Proposta: ${r.quantidade}× ${nome}.`));
  const topo = no("div", "medida-topo");
  topo.append(no("b", "taxa-grande", pct(med.taxa)), no("span", "", "de vitórias com 5 jogadores"),
    no("span", `veredito${med.dificuldade ? "" : " sem-faixa"}`, med.rotulo || ""));
  bloco.append(topo, escala(med.taxa));
  const acoes = no("div", "linha");
  if (r.quantidade !== r.antes) {
    const usar = no("button", "botao principal pequena", `Usar ${r.quantidade}× ${nome}`);
    usar.type = "button";
    usar.addEventListener("click", () => {
      caixa.replaceChildren();
      aoUsar(r.bando, r.medida);
      aviso(`Bando trocado para ${r.quantidade}× ${nome}.`);
    });
    acoes.append(usar);
  }
  const descartar = no("button", "botao discreto pequena", "Descartar");
  descartar.type = "button";
  descartar.addEventListener("click", () => caixa.replaceChildren());
  acoes.append(descartar);
  bloco.append(acoes);
  caixa.append(bloco);
}
function atualizarBotoesDeSimular() {
  if (parte === "Dungeons" && etapa === "Chefe" && rascunho()) atualizarSimulacao();
  if (parte === "Salas" && salaAberta?.origem === "nova" && salaAtual()) atualizarSimSala();
  document.querySelectorAll(".simular-caminho").forEach(b => {
    b.disabled = simulando || !!C.falta_para_simular || !inc()?.tier;
  });
  document.querySelectorAll(".ajustar").forEach(b => {
    b.disabled = simulando || !!C.falta_para_simular || !!b.dataset.aqui;
  });
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
function desenharMedida(caixa, r, velha, aoAjustar = null) {
  caixa.replaceChildren();
  caixa.className = "resultado" + (velha ? " velho" : "");
  r.medidas.forEach(med => {
    const bloco = no("div", "medida-grupo");
    const topo = no("div", "medida-topo");
    topo.append(no("b", "taxa-grande", pct(med.taxa)),
      no("span", "", `de vitórias com ${med.grupo} jogadores`),
      no("span", `veredito${med.dificuldade ? "" : " sem-faixa"}`, med.rotulo || ""));
    bloco.append(topo, escala(med.taxa));
    proximoPasso(med).forEach(d => bloco.append(no("p", "dica", d)));
    // O ajuste é do grupo de 5, que é o do jogo, e só de medida atual: ajustar
    // a partir de um número velho seria mirar com a régua de outro bando.
    if (aoAjustar && !velha && med.grupo === 5) bloco.append(botoesDeAjuste(med, aoAjustar));
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
function medidaCurta(r, velha) {
  const m = r.medidas[0] || {};
  const n = no("span", "medida-curta" + (velha ? " velho" : ""));
  n.append(no("b", "", pct(m.taxa)), " ", no("span", `veredito${m.dificuldade ? "" : " sem-faixa"}`, m.rotulo || ""));
  if (m.dizima && m.pior) n.append(no("span", "legenda", ` pior formação ${pct(m.pior.taxa)}`));
  if (velha) n.title = "Medida antes da última mudança de tier.";
  return n;
}

/* --------------------------------------------------------- 3. o chefe */

function linhasDoChefe() { return linhasDe(`chefe|${chave}`, chefe().monstros); }
function gravarChefe() {
  chefe().monstros = bandoDas(linhasDoChefe());
  $("propostaChefe").replaceChildren();
  alterado(); atualizarChefe();
}
function usarNoChefe(bando, medida) {
  chefe().monstros = bandoDas(bando);
  linhasCache.delete(`chefe|${chave}`);
  alterado();
  // A medida que confirmou a proposta é a medida do bando novo.
  rascunho().medida = {assinatura: assinatura(), resposta: medida, quando: new Date().toISOString()};
  guardar();
  mostrarChefe();
}
function mostrarChefe() {
  const o = chefe();
  $("cSala").value = texto(o.nome);
  $("cDesc").value = texto(o.descricao);
  tabelaDeCriaturas($("linhasChefe"), linhasDoChefe(), gravarChefe);
  atualizarChefe();
}
function atualizarChefe() {
  const o = chefe(), L = C.limites;
  contar("cSalaConta", texto(o.nome).length, L.aviso_titulo, L.titulo);
  contar("cDescConta", texto(o.descricao).length, L.aviso_descricao, L.descricao);
  const [frase, ruim] = recadoDoBando(o.monstros, "O chefe precisa de pelo menos uma criatura.");
  $("recadoChefe").textContent = frase;
  $("recadoChefe").classList.toggle("invalido", ruim);
  atualizarSimulacao();
}
$("cSala").addEventListener("input", () => { if (!chefe()) return; chefe().nome = $("cSala").value; alterado(); atualizarChefe(); });
$("cDesc").addEventListener("input", () => { if (!chefe()) return; chefe().descricao = $("cDesc").value; alterado(); atualizarChefe(); });
$("btCriatura").addEventListener("click", () => { if (chefe()) novaLinha($("linhasChefe"), linhasDoChefe(), gravarChefe); });

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
  if (!totalDe(chefe().monstros)) return "Adicione pelo menos uma criatura ao chefe.";
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
  if (m) {
    desenharMedida($("resultado"), m.resposta, m.assinatura !== assinatura(),
      alvo => ajustarBando(chefe().monstros, Number(inc().tier), alvo, $("propostaChefe"), usarNoChefe));
  } else {
    $("resultado").className = "resultado-vazio";
    $("resultado").textContent = "Simule para ver quantas vezes o grupo vence.";
  }
}
async function simularChefe() {
  if (simulando || motivoParaNaoSimular()) return;
  const k = chave, feita = assinatura();
  $("saidaSim").hidden = true;
  try {
    const r = await medir(chefe(), Number(inc().tier), $("btSimular"), {
      grupos: $("fSeis").checked ? [5, 6] : [5],
      semente: $("fSemente").value !== "" ? Number($("fSemente").value) : null,
    });
    if (!r) return;
    if (r.erro) { recados("saidaSim", r); return; }
    if (!rascunhos[k]) return;
    rascunhos[k].medida = {assinatura: feita, resposta: r, quando: new Date().toISOString()};
    guardar();
    if (k === chave && feita !== assinatura()) aviso("O chefe mudou durante a simulação. Simule de novo.");
  } catch (erro) { recados("saidaSim", {erro: erro.message}); }
  finally { if (k === chave && parte === "Dungeons" && etapa === "Chefe") atualizarSimulacao(); }
}
$("btSimular").addEventListener("click", simularChefe);
$("fSeis").addEventListener("change", atualizarSimulacao);
$("fSemente").addEventListener("input", atualizarSimulacao);

/* -------------------------------------------------------- 4. o caminho

   O caminho escolhe, não escreve: os temas da dungeon e as salas tiradas.
   Sala nova se escreve na parte Salas, e vai num arquivo próprio — o caminho
   só a conta, marcada como "sua", para o autor ver a dungeon que vai ter. */

function filtroDe(i) { return objeto(i.filtro) ? i.filtro : {}; }
function gravarFiltro(i, f) {
  const limpo = {};
  if (f.incluir?.length) limpo.incluir = f.incluir;
  else if (f.temas?.length) limpo.temas = C.temas.filter(t => f.temas.includes(t));
  if (f.excluir?.length) limpo.excluir = f.excluir;
  if (Object.keys(limpo).length) i.filtro = limpo; else delete i.filtro;
}
function salaCrua(org, id) {
  return locais(org).find(s => s.id === id) || salasDoBot(org).find(s => s.id === id);
}
function sorteaveisComAsSuas(org) {
  return [...salasDoBot(org), ...locais(org)].filter(s => familiaDe(s.tipo) !== "parada");
}
function desenharFichasCaminho(i) {
  const f = filtroDe(i), org = i.organizacao, marcados = f.temas || [];
  const todas = org ? sorteaveisComAsSuas(org) : [];
  fichas("fichasCaminho", C.temas, marcados, (tema, ligar) => {
    const atual = new Set(marcados);
    ligar ? atual.add(tema) : atual.delete(tema);
    gravarFiltro(i, {...f, temas: [...atual]});
    alterado(); mostrarCaminho();
  }, tema => todas.filter(s => (s.temas || []).includes(tema)).length);
  const semTema = todas.filter(s => !(s.temas || []).length).length;
  if (semTema) $("fichasCaminho").append(no("span", "legenda", `${semTema} sala(s) sem tema entram em qualquer dungeon.`));
  const fixa = !!f.incluir?.length;
  $("fichasCaminho").querySelectorAll(".ficha").forEach(b => { b.disabled = fixa || !org; });
  $("notaIncluir").hidden = !fixa;
  $("notaIncluir").replaceChildren();
  if (fixa) {
    const voltar = no("button", "link", "Escolher por tema");
    voltar.type = "button";
    voltar.addEventListener("click", () => { gravarFiltro(i, {...f, incluir: []}); alterado(); mostrarCaminho(); });
    $("notaIncluir").append(`Esta dungeon usa uma lista fixa de salas, herdada da original (${f.incluir.join(", ")}): os temas não valem. `, voltar);
  }
}
function notaDoCaminho(i, r) {
  const n = r.pool.length, tam = i.tamanho || "Média", temas = filtroDe(i).temas || [];
  if (n < r.terminar) {
    return `Uma ${tam} atravessa ${r.terminar} salas: faltam ${r.terminar - n}. `
      + (temas.length
        ? `Escreva salas com ${temas.join(" ou ")} na parte Salas, e envie o arquivo delas antes desta dungeon.`
        : "Devolva salas tiradas, ou escreva salas novas na parte Salas.");
  }
  if (n < r.folga) return `Dá para terminar. Com ${r.folga} ou mais, toda parada oferece ${C.limites.opcoes_por_passo} portas; faltam ${r.folga - n} para isso.`;
  return `Dá para terminar, e toda parada oferece ${C.limites.opcoes_por_passo} portas.`;
}
async function mostrarCaminho() {
  const i = inc(), f = filtroDe(i), id = ++pedidoCaminho;
  desenharFichasCaminho(i);
  $("saidaCaminho").hidden = true;
  $("colunaBando").textContent = i.tier ? `No tier ${i.tier}` : "Bando";
  if (!i.organizacao) {
    $("tabelaCaminho").replaceChildren();
    $("contaCaminho").textContent = "Escolha a Organização na etapa A dungeon.";
    $("notaCaminho").textContent = "As salas do caminho saem do banco dela.";
    $("barraCaminho").value = 0;
    return;
  }
  try {
    const r = await api("/api/pool", {
      organizacao: i.organizacao, tamanho: i.tamanho || "Média", tier: i.tier || null,
      filtro: f, extras: locais(i.organizacao),
    });
    if (id !== pedidoCaminho) return;
    if (r.erro) { recados("saidaCaminho", r); $("contaCaminho").textContent = "Não foi possível conferir."; return; }
    const n = r.pool.length;
    $("contaCaminho").textContent = `${n} sala(s) podem cair no caminho`;
    $("barraCaminho").max = r.folga;
    $("barraCaminho").value = Math.min(n, r.folga);
    $("barraCaminho").className = n < r.terminar ? "falta" : n < r.folga ? "aperta" : "";
    $("notaCaminho").textContent = notaDoCaminho(i, r);
    // Os problemas do filtro já estão ditos na nota, com a conta; aqui só
    // o que ela não diz — sala sua que ficou de fora, por exemplo.
    if (r.avisos.length) recados("saidaCaminho", {avisos: r.avisos});
    const fora = new Set(f.excluir || []);
    $("tabelaCaminho").replaceChildren(...r.candidatas.map(s => linhaDoCaminho(i, s, !fora.has(s.id))));
    $("legendaSalasCaminho").textContent = r.candidatas.length
      ? "Desmarque uma sala para tirá-la desta dungeon."
      : "Nenhuma sala com estes temas.";
  } catch (erro) {
    if (id === pedidoCaminho) { recados("saidaCaminho", {erro: erro.message}); $("contaCaminho").textContent = "Não foi possível conferir."; }
  }
}
function linhaDoCaminho(i, s, entra) {
  const tr = no("tr", entra ? "" : "fora");
  const marca = no("td", "entra");
  const caixa = document.createElement("input");
  caixa.type = "checkbox"; caixa.checked = entra;
  caixa.setAttribute("aria-label", `${s.nome} entra nesta dungeon`);
  caixa.addEventListener("change", () => {
    const f = filtroDe(i), tiradas = new Set(f.excluir || []);
    caixa.checked ? tiradas.delete(s.id) : tiradas.add(s.id);
    gravarFiltro(i, {...f, excluir: [...tiradas]});
    alterado(); mostrarCaminho();
  });
  marca.append(caixa);
  const nome = no("td");
  nome.append(no("small", "", s.id), no("span", "", s.nome));
  if (s.nova) nome.append(no("span", "marca-nova", "sua · envie antes da dungeon"));
  tr.append(marca, nome, no("td", "", s.tipo), no("td", "", s.temas.join(", ") || "—"));
  tr.append(s.combate ? celulaDoBando(i, s) : no("td", "legenda", "—"));
  return tr;
}
function celulaDoBando(i, s) {
  const td = no("td", "bando");
  const crua = salaCrua(i.organizacao, s.id) || {};
  if (!i.tier) {
    const tiers = Object.keys(crua.monstros_por_tier || {});
    td.append(no("span", "legenda", tiers.length ? `bandos nos tiers ${tiers.join(", ")}` : bandoEmTexto(crua.monstros)));
    return td;
  }
  const escrito = s.tier_do_bando;
  const bando = escrito == null ? crua.monstros || [] : (crua.monstros_por_tier || {})[String(escrito)] || [];
  td.append(no("span", "", bandoEmTexto(bando)));
  if (escrito != null && escrito !== Number(i.tier)) {
    td.append(no("span", "queda", `sem bando do tier ${i.tier}: usa o do tier ${escrito}`));
  }
  const linha = no("div", "linha");
  const botao = no("button", "botao pequena simular-caminho", "Simular");
  botao.type = "button";
  botao.disabled = simulando || !!C.falta_para_simular;
  const resultado = no("span", "resultado-caminho");
  const feita = JSON.stringify([i.tier, bando]);
  const guardada = rascunho().medidasCaminho?.[s.id];
  if (guardada) resultado.append(medidaCurta(guardada.resposta, guardada.assinatura !== feita));
  botao.addEventListener("click", async () => {
    const k = chave;
    try {
      const r = await medir(crua, Number(i.tier), botao);
      if (!r || !rascunhos[k]) return;
      if (r.erro) { aviso(`Não foi possível simular ${s.nome}: ${r.erro}`); return; }
      (rascunhos[k].medidasCaminho ||= {})[s.id] = {assinatura: feita, resposta: r};
      guardar();
      resultado.replaceChildren(medidaCurta(r, false));
    } catch (erro) { aviso(`Não foi possível simular ${s.nome}: ${erro.message}`); }
  });
  linha.append(botao, resultado);
  td.append(linha);
  return td;
}

/* ------------------------------------------------- 5. revisar e baixar */

/* O arquivo que sai: o mesmo formato que o bot lê. Campo opcional vazio
   sai do arquivo em vez de ir como "" — o arquivo fica legível para quem
   revisa, e o bot trata ausente e vazio igual. As salas novas NÃO vão aqui:
   elas têm o arquivo delas, na parte Salas. */
function arquivo() {
  const i = copiar(inc());
  if (!texto(i.lore_final).trim()) delete i.lore_final;
  if (!texto(i.imagem_capa).trim()) delete i.imagem_capa;
  return {
    formato: C.formato.nome, versao: C.formato.versao,
    organizacao: texto(i.organizacao), incursao: i, salas: [],
  };
}
function nomeDoArquivo() { return `${inc().id || "dungeon"}.json`; }

async function conferir() {
  const id = ++pedidoConferir, k = chave, org = inc().organizacao;
  try {
    const r = await api("/api/conferir", {dados: arquivo(), salas_do_autor: org ? locais(org) : []});
    if (id !== pedidoConferir || k !== chave) return;
    recados("saidaRevisar", r, "Pronta para enviar: o bot não encontrou nenhum problema.");
    const problemas = (r.problemas || []).length;
    $("btBaixar").textContent = problemas ? "↓ Baixar mesmo assim" : "↓ Baixar arquivo";
    $("notaArquivo").textContent = notaDoArquivo(problemas);
    if (r.caminho != null) $("resumoPool").textContent = ` · ${r.caminho} sala(s) podem cair`;
  } catch (erro) { if (id === pedidoConferir) recados("saidaRevisar", {erro: erro.message}); }
}
function notaDoArquivo(problemas) {
  const partes = [`${nomeDoArquivo()} — é este arquivo que se envia pelo Discord, com o comando “/incursao enviar”. Abrindo ele aqui de novo, você continua de onde parou.`];
  if (!rascunho().idFixo && inc().id) partes.push(`O código “${inc().id}” fica fixo a partir deste download: reenviar o arquivo atualiza a mesma dungeon, mesmo que o nome mude.`);
  if (problemas) partes.push("O bot recusa o arquivo enquanto houver problema.");
  return partes.join(" ");
}
function linhaDoResumo(rotulo, valor, destino) {
  const dt = no("dt", "", rotulo), dd = no("dd", "", valor);
  if (destino) {
    const b = no("button", "link", "mudar");
    b.type = "button";
    b.addEventListener("click", () => irPara(destino));
    dd.append(" ", b);
  }
  $("resumo").append(dt, dd);
  return dd;
}
function mostrarRevisao() {
  const i = inc(), o = chefe(), m = rascunho().medida, f = filtroDe(i);
  $("resumo").replaceChildren();
  linhaDoResumo("Dungeon", `${texto(i.nome) || "sem nome"}${i.id ? ` (${i.id})` : ""}`, "Dungeon");
  linhaDoResumo("Organização", i.organizacao || "não escolhida", "Dungeon");
  linhaDoResumo("Quem entra", i.tier ? tierRotulo(i.tier) : "tier não escolhido", "Dungeon");
  const caminho = linhaDoResumo("Caminho", `${i.tamanho || "—"}: ${resumoDoCaminho(i.tamanho)}`, "Caminho");
  caminho.insertBefore(no("span", "", ""), caminho.querySelector(".link")).id = "resumoPool";
  const filtro = [f.temas?.length ? `temas ${f.temas.join(", ")}` : f.incluir?.length ? `lista fixa: ${f.incluir.join(", ")}` : "todas as salas da Organização",
    f.excluir?.length ? `${f.excluir.length} tirada(s): ${f.excluir.join(", ")}` : ""].filter(Boolean).join(" · ");
  linhaDoResumo("Salas", filtro, "Caminho");
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
  ["Temas do caminho", i => (filtroDe(i).temas || []).join(", "), "curto"],
  ["Salas tiradas", i => (filtroDe(i).excluir || []).join(", "), "curto"],
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
  baixarJson(arquivo(), nomeDoArquivo());
  const fixou = !rascunho().idFixo && inc().id;
  rascunho().idFixo = true;
  alterado();
  if (etapa === "Revisar") $("notaArquivo").textContent = notaDoArquivo(0);
  aviso(fixou ? `Arquivo baixado. O código “${inc().id}” agora é fixo.` : "Arquivo baixado.");
}
$("btBaixar").addEventListener("click", baixar);

/* ================================================= a parte das salas

   Sala nova do autor, para o banco de uma Organização. As salas do bot
   aparecem ao lado, só para leitura: o autor altera só o que ele mesmo
   enviou, e partir de uma sala pronta é copiá-la. */

function salaAtual() {
  return salaAberta?.origem === "nova" ? locais(orgSalas).find(s => s.id === salaAberta.id) : undefined;
}
function salvarSalas() {
  guardar();
  agendarConferenciaSalas();
}
/* O código da sala nova leva um pedaço aleatório, e não o próximo número:
   dois autores escrevendo salas ao mesmo tempo pegariam os dois o "VO15", e
   o segundo envio seria recusado por um código que ele nunca viu. */
function novoIdDeSala(org) {
  const usados = new Set([...salasDoBot(org).map(s => s.id), ...locais(org).map(s => s.id)]);
  const modelo = salasDoBot(org).map(s => texto(s.id).match(/^[A-Za-z]+/)).find(Boolean);
  const prefixo = modelo ? modelo[0] : (slug(org).slice(0, 2).toUpperCase() || "SL");
  let id;
  do { id = `${prefixo}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`; } while (usados.has(id) || id.length < prefixo.length + 5);
  return id;
}
function tiposDeSala() { return C.tipos_de_sala.filter(t => t.familia !== "parada"); }
function tiersUsados(org) {
  const usados = new Set(C.tiers_por_organizacao[org] || []);
  Object.values(rascunhos).forEach(r => {
    const i = r.pacote.incursao;
    if (i.organizacao === org && i.tier) usados.add(Number(i.tier));
  });
  return [...usados].sort((a, b) => a - b);
}

function mostrarParteSalas() {
  if (!C.organizacoes.includes(orgSalas)) orgSalas = inc()?.organizacao || C.organizacoes[0];
  preencher($("sOrg"), C.organizacoes.map(o => [o, o]), orgSalas);
  listarSalas();
  mostrarSala();
  conferirSalas();
}
function itemDeSala(s, atual, aoAbrir) {
  const li = no("li");
  const b = no("button", "sala-item");
  b.type = "button";
  b.setAttribute("aria-current", atual ? "true" : "false");
  b.append(no("span", "sala-nome", texto(s.nome) || "Sala sem nome"),
    no("span", "sala-meta", `${texto(s.id)} · ${texto(s.tipo)}${(s.temas || []).length ? ` · ${s.temas.join(", ")}` : ""}`));
  b.addEventListener("click", aoAbrir);
  li.append(b);
  return li;
}
function listarSalas() {
  const org = orgSalas, novas = locais(org);
  $("listaNovas").replaceChildren(...novas.map(s => itemDeSala(s,
    salaAberta?.origem === "nova" && salaAberta.id === s.id, () => abrirSala("nova", s.id))));
  $("contaNovas").textContent = novas.length;
  $("semNovas").hidden = novas.length > 0;
  const busca = normalizar($("sBusca").value);
  const doBot = salasDoBot(org).filter(s => !busca
    || normalizar(`${s.id} ${s.nome} ${(s.temas || []).join(" ")}`).includes(busca));
  $("listaDoBot").replaceChildren(...doBot.map(s => itemDeSala(s,
    salaAberta?.origem === "bot" && salaAberta.id === s.id, () => abrirSala("bot", s.id))));
}
function abrirSala(origem, id) {
  salaAberta = {origem, id};
  linhasCache.clear();
  $("propostaSala").replaceChildren();
  const s = origem === "nova" ? salaAtual() : null;
  if (s && familiaDe(s.tipo) === "combate") tierSala = tierInicial(s);
  listarSalas();
  mostrarSala();
  if (origem === "nova") $("sNome").focus();
}
/* Abre no tier que mais precisa de bando: o primeiro usado sem bando
   escrito, senão o primeiro usado. */
function tierInicial(s) {
  const usados = tiersUsados(orgSalas), porTier = s.monstros_por_tier || {};
  return usados.find(t => !(porTier[String(t)] || []).length) || usados[0] || 1;
}
function mostrarSala() {
  const nova = salaAtual();
  const doBot = salaAberta?.origem === "bot" ? salasDoBot(orgSalas).find(s => s.id === salaAberta.id) : null;
  if (salaAberta && !nova && !doBot) salaAberta = null;
  $("salaVazia").hidden = !!(nova || doBot);
  $("salaDoBot").hidden = !doBot;
  $("editorSala").hidden = !nova;
  if (doBot) {
    $("botNome").textContent = texto(doBot.nome);
    $("botMeta").textContent = `${doBot.id} · ${doBot.tipo}${(doBot.temas || []).length ? ` · temas ${doBot.temas.join(", ")}` : " · sem tema"}`;
    previaSala($("botPrevia"), doBot);
  }
  if (nova) mostrarEditorSala(nova);
}
function previaSala(caixa, s) {
  caixa.replaceChildren();
  caixa.append(no("h3", "", texto(s.nome) || "Sala sem nome"));
  caixa.append(no("p", s.descricao ? "" : "vazio-previa", texto(s.descricao) || "Escreva a descrição."));
  const campos = no("div", "discord-campos");
  if (familiaDe(s.tipo) === "combate") {
    const porTier = s.monstros_por_tier || {};
    Object.keys(porTier).sort().forEach(t => campos.append(campoDiscord(`Tier ${t}`, bandoEmTexto(porTier[t]), false)));
    if (!Object.keys(porTier).length && (s.monstros || []).length) campos.append(campoDiscord("Criaturas", bandoEmTexto(s.monstros), false));
  } else {
    if (s.dificuldade) campos.append(campoDiscord("Dificuldade", s.dificuldade));
    if (s.cd != null) campos.append(campoDiscord("CD (tier 1)", s.cd));
    if (s.alvo_progresso != null) campos.append(campoDiscord("Sucessos", s.alvo_progresso));
    if ((s.pericias || []).length) campos.append(campoDiscord("Perícias", s.pericias.join(", "), false));
  }
  if (s.recompensa) campos.append(campoDiscord("Recompensa", s.recompensa, false));
  if (campos.children.length) caixa.append(campos);
}

function mostrarEditorSala(s) {
  const L = C.limites, fam = familiaDe(s.tipo);
  $("sNome").value = texto(s.nome);
  $("sCodigo").textContent = `Código: ${s.id}`;
  preencher($("sTipo"), tiposDeSala().map(t => [t.id, t.id]), s.tipo);
  $("sRegras").textContent = (C.tipos_de_sala.find(t => t.id === s.tipo) || {}).resumo || "";
  $("sDesc").value = texto(s.descricao);
  const temas = Array.isArray(s.temas) ? s.temas : [];
  fichas("sTemas", C.temas, temas, (tema, ligar) => {
    const atual = new Set(temas);
    ligar ? atual.add(tema) : atual.delete(tema);
    s.temas = C.temas.filter(t => atual.has(t));
    salvarSalas(); mostrarEditorSala(s); listarSalas();
  });
  $("sBlocoTeste").hidden = fam !== "teste";
  $("sBlocoCombate").hidden = fam !== "combate";
  if (fam === "teste") {
    preencher($("sDif"), C.dificuldades.map(d => [d, d]), s.dificuldade || C.dificuldades[1]);
    $("sCd").value = s.cd ?? "";
    $("sAlvo").value = s.alvo_progresso ?? "";
    const pericias = Array.isArray(s.pericias) ? s.pericias : [];
    fichas("sPericias", C.pericias, pericias, (pericia, ligar) => {
      const atual = new Set(pericias);
      ligar ? atual.add(pericia) : atual.delete(pericia);
      s.pericias = C.pericias.filter(p => atual.has(p));
      salvarSalas(); mostrarEditorSala(s);
    });
  }
  if (fam === "combate") {
    desenharAbasTier(s);
    tabelaDeCriaturas($("linhasSala"), linhasDoTier(s), () => gravarTier(s));
  }
  $("sRecompensa").value = texto(s.recompensa);
  $("sPontos").value = s.pontos_organizacao ?? "";
  atualizarEditorSala(s);
}
function atualizarEditorSala(s) {
  const L = C.limites;
  contar("sNomeConta", texto(s.nome).length, L.aviso_titulo, L.titulo);
  contar("sDescConta", texto(s.descricao).length, L.aviso_descricao, L.descricao);
  const desconto = (C.tipos_de_sala.find(t => t.id === s.tipo) || {}).desconto_cd || 0;
  $("sDicaCd").textContent = desconto && s.cd
    ? `Na mesa: ${Math.max(1, s.cd - desconto)} (−${desconto}). O tier soma o ajuste dele.` : "O tier soma o ajuste dele.";
  if (familiaDe(s.tipo) === "combate") {
    const bando = (s.monstros_por_tier || {})[String(tierSala)] || [];
    const [frase, ruim] = recadoDoBando(bando, `Sem bando no tier ${tierSala}.`);
    $("recadoSala").textContent = frase;
    $("recadoSala").classList.toggle("invalido", ruim);
    atualizarSimSala();
  }
  previaSala($("previaSala"), s);
}
function desenharAbasTier(s) {
  const usados = tiersUsados(orgSalas), porTier = s.monstros_por_tier || {};
  const abas = $("abasTier");
  abas.replaceChildren();
  for (let t = 1; t <= C.limites.tier_maximo; t++) {
    const b = no("button", "aba-tier" + (usados.includes(t) ? " usado" : ""));
    b.type = "button"; b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", t === tierSala ? "true" : "false");
    const total = totalDe(porTier[String(t)]);
    b.append(no("span", "", `Tier ${t}`), no("small", "", total ? `${total} criatura(s)` : "vazio"));
    b.title = usados.includes(t) ? "Há dungeon desta Organização neste tier." : "Nenhuma dungeon desta Organização usa este tier ainda.";
    b.addEventListener("click", () => {
      tierSala = t;
      $("propostaSala").replaceChildren();
      desenharAbasTier(s);
      tabelaDeCriaturas($("linhasSala"), linhasDoTier(s), () => gravarTier(s));
      atualizarEditorSala(s);
    });
    abas.append(b);
  }
  const faltando = usados.filter(t => !(porTier[String(t)] || []).length).map(t => {
    const escrito = tierEscritoPara(porTier, t);
    return escrito == null ? `tier ${t}` : `tier ${t} (usa o bando do tier ${escrito})`;
  });
  const partes = [usados.length
    ? `As dungeons de ${orgSalas} usam os tiers ${usados.join(", ")}.`
    : `Nenhuma dungeon de ${orgSalas} ainda.`];
  if (faltando.length) partes.push(`Sem bando próprio: ${faltando.join(", ")}.`);
  if (objeto(s.monstros_por_tema) && Object.keys(s.monstros_por_tema).length) {
    partes.push(`Variantes por tema herdadas (${Object.keys(s.monstros_por_tema).join(", ")}) vão no arquivo como estão.`);
  }
  $("sTiersUsados").textContent = partes.join(" ");
}
function linhasDoTier(s) {
  return linhasDe(`sala|${orgSalas}|${s.id}|${tierSala}`, (s.monstros_por_tier || {})[String(tierSala)]);
}
function gravarTier(s) {
  const bando = bandoDas(linhasDoTier(s));
  if (!objeto(s.monstros_por_tier)) s.monstros_por_tier = {};
  if (bando.length) s.monstros_por_tier[String(tierSala)] = bando;
  else delete s.monstros_por_tier[String(tierSala)];
  $("propostaSala").replaceChildren();
  salvarSalas();
  desenharAbasTier(s);
  atualizarEditorSala(s);
}
/* Campo que não pertence ao tipo novo sai: o validador recusa sala de
   Combate com perícia e sala de teste com criatura, e o autor não tem como
   ver o resto na tela para apagar à mão. */
function trocarTipoSala(s, tipo) {
  s.tipo = tipo;
  if (familiaDe(tipo) === "combate") {
    s.dificuldade = null; s.cd = null; s.alvo_progresso = null; s.pericias = [];
    if (!objeto(s.monstros_por_tier)) s.monstros_por_tier = {};
    tierSala = tierInicial(s);
  } else {
    delete s.monstros; delete s.monstros_por_tier; delete s.monstros_por_tema;
    s.dificuldade ||= C.dificuldades[1];
    if (s.cd == null) s.cd = 13;
    if (s.alvo_progresso == null) s.alvo_progresso = 3;
    if (!Array.isArray(s.pericias)) s.pericias = [];
  }
  linhasCache.clear();
}
function campoDaSala(id, aplicar, evento = "input") {
  $(id).addEventListener(evento, () => {
    const s = salaAtual();
    if (!s) return;
    aplicar(s, $(id).value);
    salvarSalas();
    atualizarEditorSala(s);
  });
}
campoDaSala("sNome", (s, v) => { s.nome = v; listarSalas(); });
campoDaSala("sDesc", (s, v) => { s.descricao = v; });
campoDaSala("sDif", (s, v) => { s.dificuldade = v; }, "change");
campoDaSala("sCd", s => { s.cd = numero("sCd"); });
campoDaSala("sAlvo", s => { s.alvo_progresso = numero("sAlvo"); });
campoDaSala("sRecompensa", (s, v) => { s.recompensa = v.trim() || null; });
campoDaSala("sPontos", s => { s.pontos_organizacao = numero("sPontos") ?? 0; });
$("sTipo").addEventListener("change", () => {
  const s = salaAtual();
  if (!s) return;
  trocarTipoSala(s, $("sTipo").value);
  salvarSalas(); mostrarEditorSala(s); listarSalas();
});
$("btCriaturaSala").addEventListener("click", () => {
  const s = salaAtual();
  if (s) novaLinha($("linhasSala"), linhasDoTier(s), () => gravarTier(s));
});

function assinaturaSala(s, t) { return JSON.stringify([t, (s.monstros_por_tier || {})[String(t)] || []]); }
function medidaDaSala(s, t) { return medidasSalas[`${orgSalas}|${s.id}`]?.[t]; }
function atualizarSimSala() {
  const s = salaAtual();
  if (!s) return;
  const bando = (s.monstros_por_tier || {})[String(tierSala)] || [];
  const motivo = C.falta_para_simular || (!totalDe(bando) ? `Escreva o bando do tier ${tierSala} para simular.` : "");
  $("motivoSimularSala").textContent = motivo;
  $("motivoSimularSala").hidden = !motivo;
  $("btSimularSala").disabled = simulando || !!motivo;
  $("btSimularSala").textContent = simulando ? $("btSimularSala").textContent : `Simular no tier ${tierSala}`;
  const m = medidaDaSala(s, tierSala);
  const velha = !!m && m.assinatura !== assinaturaSala(s, tierSala);
  $("medidaVelhaSala").hidden = !velha;
  const t = tierSala, org = orgSalas;
  if (m) {
    desenharMedida($("resultadoSala"), m.resposta, velha, alvo => ajustarBando(
      (s.monstros_por_tier || {})[String(t)] || [], t, alvo, $("propostaSala"), (bando, medida) => {
        if (!objeto(s.monstros_por_tier)) s.monstros_por_tier = {};
        s.monstros_por_tier[String(t)] = bandoDas(bando);
        linhasCache.delete(`sala|${org}|${s.id}|${t}`);
        (medidasSalas[`${org}|${s.id}`] ||= {})[t] = {assinatura: assinaturaSala(s, t), resposta: medida};
        salvarSalas();
        mostrarEditorSala(s);
      }));
  } else { $("resultadoSala").className = ""; $("resultadoSala").replaceChildren(); }
}
$("btSimularSala").addEventListener("click", async () => {
  const s = salaAtual();
  if (!s || simulando) return;
  const t = tierSala, org = orgSalas, feita = assinaturaSala(s, t);
  try {
    const r = await medir(s, t, $("btSimularSala"));
    if (!r) return;
    if (r.erro) { aviso(`Não foi possível simular: ${r.erro}`); return; }
    (medidasSalas[`${org}|${s.id}`] ||= {})[t] = {assinatura: feita, resposta: r};
  } catch (erro) { aviso(`Não foi possível simular: ${erro.message}`); }
  finally { atualizarSimSala(); }
});

function novaSala() {
  const s = {
    id: novoIdDeSala(orgSalas), nome: "", tipo: C.sala_nova.teste, descricao: "", temas: [],
    dificuldade: C.dificuldades[1], cd: 13, alvo_progresso: 3, pericias: [],
    recompensa: null, pontos_organizacao: 2,
  };
  locais(orgSalas).push(s);
  salvarSalas();
  abrirSala("nova", s.id);
}
function copiarSalaDoBot() {
  const original = salasDoBot(orgSalas).find(s => s.id === salaAberta?.id);
  if (!original) return;
  const s = copiar(original);
  s.id = novoIdDeSala(orgSalas);
  s.nome = `${texto(original.nome)} (cópia)`;
  locais(orgSalas).push(s);
  salvarSalas();
  abrirSala("nova", s.id);
  aviso(`Cópia de “${texto(original.nome)}” criada como sala nova ${s.id}.`);
}
function apagarSala() {
  const s = salaAtual();
  if (!s || !confirm(`Apagar a sala “${texto(s.nome) || s.id}” deste navegador? Isso não tem volta — um arquivo que você já baixou continua no seu computador.`)) return;
  salasLocais[orgSalas] = locais(orgSalas).filter(x => x.id !== s.id);
  delete medidasSalas[`${orgSalas}|${s.id}`];
  salaAberta = null;
  linhasCache.clear();
  salvarSalas(); listarSalas(); mostrarSala();
}

/* O arquivo de salas: só as salas novas desta Organização. Vai antes de
   qualquer dungeon que conte com elas — sem elas no bot, a dungeon que
   depende delas é recusada. */
function pacoteDeSalas(org) {
  return {formato: C.formato.nome, versao: C.formato.versao, organizacao: org, salas: copiar(locais(org))};
}
function nomeArquivoSalas(org) { return `salas_${slug(org)}.json`; }
function agendarConferenciaSalas() {
  clearTimeout(timerSalas);
  timerSalas = setTimeout(conferirSalas, 500);
}
async function conferirSalas() {
  const org = orgSalas, lista = locais(org), id = ++pedidoSalas;
  $("tituloArquivoSalas").textContent = `O arquivo de salas de ${org}`;
  $("btBaixarSalas").disabled = !lista.length;
  $("btBaixarSalas").textContent = "↓ Baixar arquivo de salas";
  $("notaArquivoSalas").textContent = lista.length
    ? `${nomeArquivoSalas(org)} — ${lista.length} sala(s) nova(s). Envie este arquivo pelo Discord, com o comando “/incursao enviar”, antes de qualquer dungeon que conte com elas.`
    : "Sem sala nova nesta Organização, não há arquivo para baixar.";
  if (!lista.length) { $("saidaSalas").hidden = true; return; }
  try {
    const r = await api("/api/conferir", {dados: pacoteDeSalas(org)});
    if (id !== pedidoSalas || org !== orgSalas) return;
    recados("saidaSalas", r, "Prontas para enviar: o bot não encontrou nenhum problema.");
    if ((r.problemas || []).length) $("btBaixarSalas").textContent = "↓ Baixar mesmo assim";
  } catch (erro) { if (id === pedidoSalas) recados("saidaSalas", {erro: erro.message}); }
}
function baixarSalas() {
  const lista = locais(orgSalas);
  if (!lista.length) return;
  baixarJson(pacoteDeSalas(orgSalas), nomeArquivoSalas(orgSalas));
  aviso(`Arquivo de salas de ${orgSalas} baixado.`);
}
/* Abrir um arquivo de salas baixado antes junta as salas dele às do
   navegador, pelo código: a do arquivo substitui a de mesmo código. */
async function abrirArquivoSalas(evento) {
  const entrada = evento.target.files[0];
  evento.target.value = "";
  if (!entrada || !C) return;
  try {
    const dados = JSON.parse(await entrada.text());
    if (!objeto(dados) || dados.formato !== C.formato.nome) throw new Error("este arquivo não foi gerado pelo Estúdio.");
    if (objeto(dados.incursao)) throw new Error("este arquivo é de uma dungeon. Abra-o na parte Dungeons.");
    if (!C.organizacoes.includes(dados.organizacao) || !Array.isArray(dados.salas)) throw new Error("o arquivo não diz a Organização ou as salas.");
    const lista = locais(dados.organizacao);
    dados.salas.filter(objeto).forEach(s => {
      const i = lista.findIndex(x => x.id === s.id);
      if (i >= 0) lista[i] = s; else lista.push(s);
    });
    orgSalas = dados.organizacao;
    salaAberta = null;
    linhasCache.clear();
    salvarSalas();
    mostrarParteSalas();
    aviso(`${dados.salas.length} sala(s) de ${orgSalas} abertas.`);
  } catch (erro) { aviso(`Não foi possível abrir: ${erro.message}`); }
}

$("sOrg").addEventListener("change", () => { orgSalas = $("sOrg").value; salaAberta = null; linhasCache.clear(); mostrarParteSalas(); });
$("sBusca").addEventListener("input", listarSalas);
$("btNovaSala").addEventListener("click", () => { if (C) novaSala(); });
$("btCopiarSala").addEventListener("click", copiarSalaDoBot);
$("btApagarSala").addEventListener("click", apagarSala);
$("btBaixarSalas").addEventListener("click", baixarSalas);
$("btAbrirSalas").addEventListener("click", () => { if (C) $("fArquivoSalas").click(); });
$("fArquivoSalas").addEventListener("change", abrirArquivoSalas);

/* ------------------------------------------------------------- início */

async function iniciar() {
  try {
    C = await api("/api/conteudo");
    (C.criaturas || []).forEach(nome => BESTIARIO.add(nome));
    $("listaCriaturas").replaceChildren(...(C.criaturas || []).map(nome => { const o = document.createElement("option"); o.value = nome; return o; }));
    [["tNome", C.limites.titulo], ["tLore", C.limites.descricao], ["tLoreFinal", C.limites.descricao],
     ["tSala", C.limites.titulo], ["tDesc", C.limites.descricao],
     ["tSNome", C.limites.titulo], ["tSDesc", C.limites.descricao]].forEach(([id, n]) => { $(id).textContent = n; });
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

document.querySelectorAll(".partes [data-parte]").forEach(b => b.addEventListener("click", () => { if (C) irParte(b.dataset.parte); }));
document.querySelectorAll(".passos [data-etapa]").forEach(b => b.addEventListener("click", () => irPara(b.dataset.etapa)));
$("btVoltar").addEventListener("click", () => passo(-1));
$("btProximo").addEventListener("click", () => passo(1));
$("btNova").addEventListener("click", () => { if (C) criarNova(); });
$("btAbrirArquivo").addEventListener("click", () => { if (C) $("fArquivo").click(); });
$("fArquivo").addEventListener("change", abrirArquivo);
document.addEventListener("keydown", evento => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "s") {
    evento.preventDefault();
    if (parte === "Salas") baixarSalas();
    else if (rascunho()) baixar();
  }
});
window.addEventListener("beforeunload", guardar);
iniciar();
