"use strict";

const $ = id => document.getElementById(id);
const copiar = valor => JSON.parse(JSON.stringify(valor));
const objeto = valor => valor !== null && typeof valor === "object" && !Array.isArray(valor);
const texto = valor => valor == null ? "" : String(valor);
const bonito = valor => JSON.stringify(valor, null, 2);
const normalizar = valor => texto(valor).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const ns = "incursoes.estudio.v2.";
let C, banco, origem, arquivo, indice = -1;
/* Os quatro lugares da bancada, e qual sala esta aberta em cada um.
   `bancadaEm` e o ultimo lugar de ESCRITA (Teste ou Combate): quem vai
   montar a dungeon e volta tem de reencontrar a sala onde a deixou. */
let lugar = "Teste", bancadaEm = "Teste";
const selecao = {Teste: -1, Combate: -1};
// Familia, resumo e desconto de CD de cada tipo, vindos de /api/conteudo.
let FAMILIA = {}, RESUMO = {}, DESCONTO = {};
const tiposVisiveis = new Set(), temasVisiveis = new Set();
// As linhas da tabela de criaturas, enquanto a sala esta aberta.
let linhasAtuais = null, linhasDoIndice = -1;
let originais = {}, sequencia = 0, revisao = 0, medindo = false, sugerindo = false;
let medidaContexto, sugestaoContexto, timerPool, timerConferir, timerToast;
let pedidoConferir = 0, pedidoPool = 0, armazenamentoFalhou = false;

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
function lerLocal(chave) {
  try { return JSON.parse(localStorage.getItem(ns + chave)); } catch { return null; }
}
function gravarLocal(chave, valor) {
  try { localStorage.setItem(ns + chave, JSON.stringify(valor)); }
  catch {
    if (!armazenamentoFalhou) aviso("Não foi possível guardar o rascunho. Baixe o JSON para salvar.");
    armazenamentoFalhou = true;
  }
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
  caixa.className = "recados " + (r.erro || problemas.length ? "erro" : avisos.length ? "aviso" : "ok");
  caixa.hidden = false;
  caixa.append(no("strong", "", r.erro || (problemas.length ? `${problemas.length} problema(s)` : avisos.length ? `${avisos.length} aviso(s)` : sucesso)));
  const mensagens = [...problemas, ...avisos];
  if (mensagens.length) {
    const lista = no("ul");
    mensagens.slice(0, 3).forEach(m => lista.append(no("li", "", m)));
    caixa.append(lista);
    if (mensagens.length > 3) {
      const detalhes = no("details"), resto = no("ul");
      detalhes.append(no("summary", "", `Ver mais ${mensagens.length - 3}`));
      mensagens.slice(3).forEach(m => resto.append(no("li", "", m)));
      detalhes.append(resto); caixa.append(detalhes);
    }
  }
}
function preencher(id, itens, escolhido) {
  preencherSelect($(id), itens.map(i => Array.isArray(i) ? i : [i, i]), texto(escolhido));
}
function preencherSelect(alvo, pares, escolhido) {
  alvo.replaceChildren();
  pares.forEach(([valor, rotulo]) => {
    const o = document.createElement("option");
    o.value = valor; o.textContent = rotulo;
    if (texto(valor) === texto(escolhido)) o.selected = true;
    alvo.append(o);
  });
}
function sala() { return indice < 0 ? undefined : banco?.salas[indice]; }
function contexto() {
  return JSON.stringify([origem, indice, revisao, $("fTierSim").value, $("fTemaSim").value,
    $("fClasse").value, $("fNivel").value, $("fReps").value, $("fSemente").value,
    [...document.querySelectorAll('[name="grupo"]:checked')].map(n => n.value)]);
}
function guardar() {
  if (!banco || !origem) return;
  gravarLocal(origem, {banco, arquivo, indice, original: originais[origem]});
  gravarLocal("ultimo", origem);
  $("estado").textContent = armazenamentoFalhou ? "Baixe o JSON para salvar" : "Rascunho neste navegador";
}
/* A conferencia da FORMA de um arquivo aberto do disco. O formulario nao
   deixa o autor escrever um banco torto, mas `importar` abre o que vier, e
   sem isto um arquivo qualquer virava `banco` e quebrava a tela em vez de
   avisar. */
function estrutura(dados, bancoInteiro) {
  if (!objeto(dados)) throw new Error("Use um objeto JSON entre { e }.");
  if (bancoInteiro && (typeof dados.organizacao !== "string" || !Array.isArray(dados.salas) || !dados.salas.every(objeto))) {
    throw new Error('O banco precisa de "organizacao" e de uma lista "salas" com objetos.');
  }
}

/* ------------------------------------------------- tipos e famílias

   A familia de um tipo diz o que o autor FAZ ao escrever a sala, e e o que
   divide a bancada em lugares. Ela vem do servidor junto com os tipos: um
   tipo novo no bot aparece aqui sem ninguem lembrar de mexer na pagina.
   Tipo desconhecido cai em "teste" para a sala continuar visivel e
   editavel — sumir da tela seria pior do que aparecer no lugar errado. */
function familia(tipo) { return FAMILIA[tipo] || "teste"; }
function lugarDoTipo(tipo) { return familia(tipo) === "combate" ? "Combate" : "Teste"; }
function tipoNovo(fam) { return (C.sala_nova || {})[fam]; }
function tiposDoLugar(atual) {
  const quero = bancadaEm === "Combate" ? ["combate"] : ["teste"];
  const lista = C.tipos.filter(t => quero.includes(familia(t)));
  // O tipo da sala aberta entra sempre, mesmo fora da familia do lugar: um
  // select que nao tem o valor da sala mostra OUTRA coisa e mente calado.
  if (atual && !lista.includes(atual)) lista.unshift(atual);
  return lista;
}

function fichas(alvo, lista, marcados, aoTrocar) {
  const caixa = $(alvo);
  caixa.replaceChildren();
  lista.forEach(item => {
    const b = no("button", "ficha", item);
    b.type = "button";
    b.setAttribute("aria-pressed", marcados.includes(item) ? "true" : "false");
    b.addEventListener("click", () => {
      const tem = marcados.includes(item);
      aoTrocar(item, !tem);
      alterado();
    });
    caixa.append(b);
  });
}

function numero(id) {
  const bruto = $(id).value.trim();
  if (bruto === "") return null;
  const n = Number(bruto);
  return Number.isFinite(n) ? n : null;
}

/* As criaturas em LINHAS, e nao aninhadas: `monstros`, `monstros_por_tier` e
   `monstros_por_tema` sao a mesma coisa vista de tres jeitos, e uma tabela de
   (criatura, quantas, tier, tema) escreve as tres sem o autor saber que elas
   existem. A volta — de linhas para os tres campos — fica em `montarMonstros`. */
function linhasDaSala(s) {
  const saida = [];
  (s.monstros || []).forEach(m => saida.push({...m, tier: "", tema: ""}));
  Object.entries(s.monstros_por_tier || {}).forEach(([tier, lista]) =>
    (lista || []).forEach(m => saida.push({...m, tier, tema: ""})));
  Object.entries(s.monstros_por_tema || {}).forEach(([tema, porTier]) =>
    Object.entries(porTier || {}).forEach(([tier, lista]) =>
      (lista || []).forEach(m => saida.push({...m, tier, tema}))));
  return saida;
}

function montarMonstros(s, linhas) {
  delete s.monstros; delete s.monstros_por_tier; delete s.monstros_por_tema;
  linhas.forEach(l => {
    const nome = texto(l.nome).trim();
    if (!nome) return;
    const bicho = {nome};
    const q = Number(l.quantidade);
    if (Number.isFinite(q) && q > 1) bicho.quantidade = q;
    if (!l.tier) { (s.monstros ||= []).push(bicho); return; }
    if (!l.tema) {
      ((s.monstros_por_tier ||= {})[l.tier] ||= []).push(bicho);
      return;
    }
    (((s.monstros_por_tema ||= {})[l.tema] ||= {})[l.tier] ||= []).push(bicho);
  });
}

function desenharCriaturas(reconstruir = false) {
  const s = sala();
  const corpo = $("linhasCriaturas");
  corpo.replaceChildren();
  if (!s) return;
  if (reconstruir || linhasAtuais === null || linhasDoIndice !== indice) {
    linhasAtuais = linhasDaSala(s);
    linhasDoIndice = indice;
  }
  const linhas = linhasAtuais;
  const temas = Array.isArray(s.temas) ? s.temas : [];
  linhas.forEach((l, i) => {
    const tr = no("tr");

    const nome = no("td");
    const campoNome = document.createElement("input");
    campoNome.type = "text"; campoNome.value = texto(l.nome);
    campoNome.setAttribute("list", "listaCriaturas");
    campoNome.addEventListener("input", () => { linhas[i].nome = campoNome.value; gravarLinhas(linhas); });
    nome.append(campoNome); tr.append(nome);

    const quantas = no("td", "n");
    const campoQ = document.createElement("input");
    campoQ.type = "number"; campoQ.min = "1"; campoQ.max = String(C.limites.inimigos);
    campoQ.value = String(l.quantidade || 1);
    campoQ.addEventListener("input", () => { linhas[i].quantidade = campoQ.value; gravarLinhas(linhas); });
    quantas.append(campoQ); tr.append(quantas);

    const tier = no("td");
    const campoT = document.createElement("select");
    preencherSelect(campoT, [["", "qualquer"]].concat(
      Array.from({length: C.limites.tier_maximo}, (_, n) => [String(n + 1), `tier ${n + 1}`])), texto(l.tier));
    campoT.addEventListener("change", () => { linhas[i].tier = campoT.value; gravarLinhas(linhas); });
    tier.append(campoT); tr.append(tier);

    const tema = no("td");
    const campoTema = document.createElement("select");
    preencherSelect(campoTema, [["", "padrão"]].concat(temas.map(t => [t, t])), texto(l.tema));
    campoTema.disabled = !l.tier || !temas.length;
    campoTema.title = temas.length ? "" : "A sala precisa ter tema para ter variante.";
    campoTema.addEventListener("change", () => { linhas[i].tema = campoTema.value; gravarLinhas(linhas); });
    tema.append(campoTema); tr.append(tema);

    const fora = no("td");
    const botao = no("button", "botao discreto pequena", "×");
    botao.type = "button"; botao.title = "Remover";
    botao.addEventListener("click", () => { linhas.splice(i, 1); gravarLinhas(linhas); desenharCriaturas(); });
    fora.append(botao); tr.append(fora);

    corpo.append(tr);
  });
  contarBando();
}

/* O limite de criaturas é POR BANDO — o que entra na mesa de uma vez —, e
   não a soma do que está escrito na sala: o bot cobra `MAX_INIMIGOS` por
   tier (e por variante de tema), porque é um tier por incursão. Somando os
   tiers, o estúdio pintava de vermelho uma sala que ele mesmo aprova em
   /api/conferir, e mandava o autor apagar criatura que não sobrava.

   Linha sem nome não conta: é um campo em branco esperando o autor, e
   `montarMonstros` também a ignora ao escrever no objeto. */
function bandos() {
  const contagem = new Map();
  (linhasAtuais || []).forEach(l => {
    if (!texto(l.nome).trim()) return;
    const chave = l.tier ? `tier ${l.tier}${l.tema ? ` · ${l.tema}` : ""}` : "sem tier";
    contagem.set(chave, (contagem.get(chave) || 0) + Math.max(1, Number(l.quantidade) || 1));
  });
  return [...contagem].sort((a, b) => b[1] - a[1]);
}

function contarBando() {
  const todos = bandos(), teto = C.limites.inimigos;
  const recado = $("recadoCriaturas");
  if (!todos.length) {
    recado.textContent = "Sala de Combate sem criatura não passa na validação.";
    recado.classList.remove("invalido");
    return;
  }
  const [maiorNome, maior] = todos[0], estoura = maior > teto;
  const excesso = estoura ? ` — o máximo é ${teto} por bando` : "";
  recado.textContent = todos.length > 1
    ? `${todos.length} bandos · o maior tem ${maior} criatura(s) em ${maiorNome}${excesso}.`
    : `${maior} criatura(s) no bando${estoura ? ` — o máximo é ${teto}` : ""}.`;
  recado.classList.toggle("invalido", estoura);
}

function gravarLinhas(linhas) {
  const s = sala();
  if (!s) return;
  montarMonstros(s, linhas);
  contarBando();
  alterado();
}

/* ------------------------------------------------------- o formulário */

function mostrarEditor() {
  const s = sala();
  if (linhasDoIndice !== indice) { linhasAtuais = null; linhasDoIndice = -1; }
  const form = $("formSala");
  form.hidden = !s;
  if (!s) { $("dicaTipo").textContent = ""; previa(); controles(); return; }

  $("fId").value = texto(s.id);
  $("fNome").value = texto(s.nome);
  $("fDesc").value = texto(s.descricao);
  $("fPontos").value = s.pontos_organizacao ?? 0;
  $("fRecompensa").value = texto(s.recompensa);
  $("fImagem").value = texto(s.imagem);
  preencherSelect($("fTipo"), tiposDoLugar(s.tipo).map(t => [t, t]), s.tipo);
  preencherSelect($("fDif"), C.dificuldades.map(d => [d, d]), texto(s.dificuldade) || C.dificuldades[1]);
  $("fCd").value = s.cd ?? "";
  $("fAlvo").value = s.alvo_progresso ?? "";
  $("dicaTipo").textContent = RESUMO[s.tipo] || "";

  const temas = Array.isArray(s.temas) ? s.temas : [];
  fichas("fichasSala", C.temas, temas, (tema, ligar) => {
    const atual = new Set(Array.isArray(s.temas) ? s.temas : []);
    ligar ? atual.add(tema) : atual.delete(tema);
    s.temas = C.temas.filter(t => atual.has(t));
    if (!s.temas.length) delete s.temas;
    mostrarEditor();
  });
  const pericias = Array.isArray(s.pericias) ? s.pericias : [];
  fichas("fichasPericias", C.pericias, pericias, (pericia, ligar) => {
    const atual = new Set(Array.isArray(s.pericias) ? s.pericias : []);
    ligar ? atual.add(pericia) : atual.delete(pericia);
    s.pericias = C.pericias.filter(p => atual.has(p));
    mostrarEditor();
  });

  contadores();
  $("blocoTeste").hidden = familia(s.tipo) !== "teste";
  $("blocoCriaturas").hidden = familia(s.tipo) !== "combate";
  if (familia(s.tipo) === "combate") desenharCriaturas();
  previa(); controles();
}

/* O formulario escreve direto no objeto, campo a campo. Nao ha "aplicar":
   o que esta na tela e o que esta no banco, sempre. */
function contadores() {
  const marcar = (alvo, quantos, aviso, teto) => {
    $(alvo).textContent = quantos;
    $(alvo).classList.toggle("invalido", quantos > teto);
    $(alvo).classList.toggle("atencao", quantos > aviso && quantos <= teto);
  };
  marcar("cNome", $("fNome").value.length, 80, C.limites.titulo);
  marcar("cDesc", $("fDesc").value.length, 600, C.limites.descricao);
  $("tetoNome").textContent = C.limites.titulo;
  $("tetoDesc").textContent = C.limites.descricao;
  $("dicaDesc").textContent = `aviso em 600 · o Discord recusa acima de ${C.limites.descricao}`;
  const s = sala(), desconto = s ? (DESCONTO[s.tipo] || 0) : 0, cd = numero("fCd");
  $("dicaCd").textContent = desconto && cd
    ? `${s.tipo} desconta ${desconto}: vale ${Math.max(1, cd - desconto)} na mesa.` : "";
}

function lerCampo(id, aplicar) {
  $(id).addEventListener("input", () => {
    const s = sala();
    if (!s) return;
    aplicar(s);
    contadores();
    alterado();
  });
}

function pronto() { return !!banco; }

function controles() {
  const temSala = !!sala(), pode = !!banco;
  ["btBaixar", "btConferirBanco", "btNova", "btCopiarFiltro"].forEach(id => { $(id).disabled = !pode; });
  ["btDuplicar", "btExcluir", "btConferir", "btVirar"].forEach(id => { $(id).disabled = !pode || !temSala; });
  $("btRecarregar").disabled = !banco;
  $("btVirar").textContent = bancadaEm === "Combate" ? "Virar sala de teste" : "Virar combate";
  const combate = temSala && familia(sala().tipo) === "combate";
  $("avisoCombate").hidden = combate || lugar !== "Combate";
  $("btMedir").disabled = !pode || !combate || medindo;
  $("btSugerir").disabled = !pode || !combate || sugerindo;
  document.querySelectorAll(".usar-sugestao").forEach(n => { n.disabled = !pode || sugestaoContexto !== contexto(); });
}

/* ----------------------------------------------------- os quatro lugares */

function indicesDoLugar(nome = bancadaEm) {
  if (!banco) return [];
  return banco.salas.reduce((saida, s, i) => {
    if (lugarDoTipo(s.tipo) === nome) saida.push(i);
    return saida;
  }, []);
}

function entrar(nome, foco = false) {
  const anterior = bancadaEm;
  lugar = nome;
  if (nome === "Teste" || nome === "Combate") bancadaEm = nome;
  document.querySelectorAll("[data-lugar]").forEach(n => {
    const ativo = n.dataset.lugar === nome;
    n.setAttribute("aria-selected", ativo); n.tabIndex = ativo ? 0 : -1;
    $("painel" + n.dataset.lugar).hidden = !ativo;
    if (ativo && foco) n.focus();
  });
  // A bancada acompanha `bancadaEm` mesmo quando o painel aberto é outro:
  // quem vai montar a dungeon e volta reencontra a sala onde a deixou.
  $("ancora" + bancadaEm).append($("bancada"));
  $("tituloLista").textContent = bancadaEm === "Combate" ? "Combates" : "Salas de teste";
  $("btNova").textContent = bancadaEm === "Combate" ? "+ Novo combate" : "+ Nova sala";
  if (anterior !== bancadaEm) $("fBusca").value = "";
  const disponiveis = indicesDoLugar(bancadaEm), guardado = selecao[bancadaEm];
  indice = disponiveis.includes(guardado) ? guardado : (disponiveis[0] ?? -1);
  selecao[bancadaEm] = indice;
  mostrarEditor();
  atualizar();
  if (nome === "Inspecao") conferir(true);
}

function abrirSala(i) {
  const destino = lugarDoTipo(banco.salas[i].tipo);
  selecao[destino] = i;
  entrar(destino);
  guardar(); agendarConferencia();
}

function listar() {
  const busca = normalizar($("fBusca").value), lista = $("listaSalas");
  lista.replaceChildren();
  const meus = indicesDoLugar();
  meus.forEach(i => {
    const s = banco.salas[i];
    if (!normalizar(`${texto(s.id)} ${texto(s.nome)}`).includes(busca)) return;
    const botao = no("button", "sala-btn"); botao.type = "button";
    botao.setAttribute("aria-current", i === indice ? "true" : "false");
    botao.append(no("span", "snome", s.nome || "Sem nome"));
    const meta = no("span", "sala-meta");
    meta.append(no("span", "sid", s.id || "Sem ID"), no("span", "", s.tipo || "Sem tipo"));
    botao.append(meta);
    botao.addEventListener("click", () => {
      if (!pronto()) return;
      indice = i; selecao[bancadaEm] = i;
      mostrarEditor(); atualizar(); guardar(); agendarConferencia();
    });
    const item = no("li"); item.append(botao); lista.append(item);
  });
  $("contaSalas").textContent = meus.length;
  $("listaVazia").hidden = lista.children.length > 0;
  $("notaLista").textContent = bancadaEm === "Combate"
    ? "O tier da incursão escolhe quem aparece em cada combate."
    : banco.salas.some(s => familia(s.tipo) === "parada")
      ? "O Descanso desta lista é parada fixa: ele não é sorteado."
      : "Este banco não tem sala de Descanso.";
}

function contas() {
  if (!banco) return;
  $("contaTeste").textContent = indicesDoLugar("Teste").length;
  $("contaCombate").textContent = indicesDoLugar("Combate").length;
  $("contaTudo").textContent = banco.salas.length;
}

/* ---------------------------------------------------------- inspecionar */

function sorteaveis() {
  return banco.salas.filter(s => familia(s.tipo) !== "parada");
}

function dentroDa(s) {
  if (familia(s.tipo) === "parada") return "";
  if (familia(s.tipo) === "combate") {
    const linhas = linhasDaSala(s);
    if (!linhas.length) return "";
    const tiers = [...new Set(linhas.map(l => l.tier).filter(Boolean))].sort();
    const variantes = [...new Set(linhas.map(l => l.tema).filter(Boolean))];
    const nomes = [...new Set(linhas.map(l => texto(l.nome).trim()).filter(Boolean))];
    const partes = [tiers.length ? `tiers ${tiers.join(", ")}` : "qualquer tier"];
    if (variantes.length) partes.push(`variantes: ${variantes.join(", ")}`);
    partes.push(nomes.slice(0, 3).join(", ") + (nomes.length > 3 ? ` +${nomes.length - 3}` : ""));
    return partes.join(" · ");
  }
  const desconto = DESCONTO[s.tipo] || 0, partes = [];
  if (s.dificuldade) partes.push(s.dificuldade);
  if (s.cd != null) partes.push(desconto ? `CD ${s.cd} → ${Math.max(1, s.cd - desconto)}` : `CD ${s.cd}`);
  if (s.alvo_progresso != null) partes.push(`${s.alvo_progresso} sucesso(s)`);
  if (Array.isArray(s.pericias) && s.pericias.length) partes.push(s.pericias.join(", "));
  return partes.join(" · ");
}

function cartao(titulo, conteudo) {
  const n = no("section");
  n.append(no("h4", "", titulo), conteudo);
  return n;
}

function mapa() {
  const caixa = $("mapaBanco");
  caixa.replaceChildren();
  const pool = sorteaveis().length;

  // O caminho: quais tamanhos este banco consegue montar, com a conta do
  // sorteio (precisa de `folga` salas para oferecer 3 portas em toda parada).
  const caminhos = no("div", "contas");
  Object.entries(C.tamanhos).forEach(([nome, t]) => {
    const linha = no("div", "conta-linha");
    const veredito = pool >= t.folga ? "com folga" : pool >= t.terminar ? "sem variedade" : "não fecha";
    const marca = no("b", "", veredito);
    marca.style.color = `var(--${pool >= t.folga ? "good" : pool >= t.terminar ? "warn" : "bad"})`;
    linha.append(no("span", "", `${nome} · ${t.paradas} paradas · quer ${t.folga}`), marca);
    caminhos.append(linha);
  });
  // O mapa dos temas são as fichas do filtro aqui embaixo, que já trazem a
  // contagem e ainda filtram a tabela. O que falta a elas é isto: sala SEM
  // tema não aparece em ficha nenhuma, e entra em toda dungeon.
  const semTema = sorteaveis().filter(s => !(s.temas || []).length).length;
  const bloco = no("div");
  bloco.append(caminhos, no("p", "legenda nota-mapa",
    `"Quer" é o que mantém ${C.limites.opcoes_por_passo} portas em toda parada. `
    + (semTema
      ? `${semTema} sala(s) estão sem tema e entram em TODA dungeon, filtrada ou não.`
      : "Toda sala sorteável tem tema.")));
  caixa.append(cartao(`O caminho · ${pool} salas sorteáveis`, bloco));

  // Os combates, e o que eles escrevem por tier.
  const combates = banco.salas.filter(s => familia(s.tipo) === "combate");
  const porTier = combates.filter(s => objeto(s.monstros_por_tier)).length;
  const comVariante = combates.filter(s => objeto(s.monstros_por_tema)).length;
  const vazias = combates.filter(s => !linhasDaSala(s).length).length;
  const contas = no("div", "contas");
  [["Salas de combate", combates.length],
   ["Com criaturas por tier", porTier],
   ["Com variante por tema", comVariante],
   ["Sem nenhuma criatura", vazias]].forEach(([rotulo, valor]) => {
    const linha = no("div", "conta-linha");
    const b = no("b", "", valor);
    if (rotulo.startsWith("Sem") && valor) b.style.color = "var(--bad)";
    linha.append(no("span", "", rotulo), b);
    contas.append(linha);
  });
  caixa.append(cartao("Combates", contas));

  $("resumoBanco").textContent =
    `${banco.salas.length} salas em ${texto(banco.organizacao)} · arquivo ${texto(arquivo)}`;
}

function filtrosDaInspecao() {
  const tipos = $("fichasTipos"), temas = $("fichasTemasInspecao");
  tipos.replaceChildren(); temas.replaceChildren();
  const alternar = (conjunto, valor, botao) => {
    conjunto.has(valor) ? conjunto.delete(valor) : conjunto.add(valor);
    botao.setAttribute("aria-pressed", conjunto.has(valor));
    inspecionar();
  };
  C.tipos.forEach(t => {
    const quantas = banco.salas.filter(s => s.tipo === t).length;
    if (!quantas) return;
    const b = no("button", "ficha", t); b.type = "button";
    b.append(no("span", "quantas", quantas));
    b.setAttribute("aria-pressed", tiposVisiveis.has(t));
    b.addEventListener("click", () => alternar(tiposVisiveis, t, b));
    tipos.append(b);
  });
  C.temas.forEach(t => {
    const quantas = banco.salas.filter(s => (s.temas || []).includes(t)).length;
    // Tema sem sala fica visível e apagado: ele é o buraco do banco, e
    // esconder o buraco é esconder o trabalho que falta.
    const b = no("button", "ficha" + (quantas ? "" : " zero"), t); b.type = "button";
    b.append(no("span", "quantas", quantas));
    b.disabled = !quantas;
    b.setAttribute("aria-pressed", temasVisiveis.has(t));
    b.addEventListener("click", () => alternar(temasVisiveis, t, b));
    temas.append(b);
  });
}

function inspecionar() {
  if (!banco) return;
  mapa();
  filtrosDaInspecao();
  const busca = normalizar($("fBuscaInspecao").value);
  const corpo = $("tabelaInspecao");
  corpo.replaceChildren();
  let quantas = 0;
  banco.salas.forEach((s, i) => {
    if (tiposVisiveis.size && !tiposVisiveis.has(s.tipo)) return;
    if (temasVisiveis.size && !(s.temas || []).some(t => temasVisiveis.has(t))) return;
    const dentro = dentroDa(s);
    if (busca && !normalizar(`${texto(s.id)} ${texto(s.nome)} ${dentro}`).includes(busca)) return;
    quantas++;
    const tr = no("tr");

    const primeira = no("td");
    const abrir = no("button", "abrir-sala"); abrir.type = "button";
    abrir.append(no("small", "", s.id || "sem id"), no("span", "", s.nome || "Sem nome"));
    abrir.addEventListener("click", () => abrirSala(i));
    primeira.append(abrir); tr.append(primeira);

    const tipo = no("td");
    const etiqueta = no("span", "etiqueta" + (familia(s.tipo) === "combate" ? " combate" : ""), s.tipo || "sem tipo");
    tipo.append(etiqueta); tr.append(tipo);

    tr.append(no("td", "", (s.temas || []).join(", ") || "—"));
    tr.append(no("td", "dentro" + (dentro ? "" : " nada"), dentro || "—"));
    tr.append(no("td", "n", s.pontos_organizacao ?? 0));
    corpo.append(tr);
  });
  $("contaInspecao").textContent = quantas;
  $("inspecaoVazia").hidden = quantas > 0;
}

/* ------------------------------------------------------------- a prévia */

function previa() {
  const s = sala();
  $("nomeSala").textContent = s?.nome || "Selecione uma sala";
  $("tipoSala").textContent = s?.tipo || "Sala";
  $("tipoSala").classList.toggle("combate", !!s && familia(s.tipo) === "combate");
  $("idSala").textContent = texto(s?.id);
  $("dTitulo").textContent = s?.nome || "Sua sala aparece aqui";
  $("dCorpo").textContent = texto(s?.descricao);
  $("dCampos").replaceChildren(); $("temasPrevia").replaceChildren();
  if (!s) { $("limitesTexto").textContent = ""; return; }
  function campo(nome, valor) {
    if (valor == null || valor === "") return;
    const n = no("div"); n.append(no("strong", "", nome), no("span", "", valor)); $("dCampos").append(n);
  }
  if (familia(s.tipo) === "combate") {
    const tiers = objeto(s.monstros_por_tier) ? Object.keys(s.monstros_por_tier) : [];
    campo("Criaturas", tiers.length ? `Tiers ${tiers.join(", ")}` : Array.isArray(s.monstros) ? s.monstros.map(m => `${m.quantidade || 1}× ${texto(m.nome)}`).join(", ") : "Não definidas");
    campo("Variantes", objeto(s.monstros_por_tema) ? Object.keys(s.monstros_por_tema).join(", ") : "");
  } else if (familia(s.tipo) === "teste") {
    campo("Dificuldade", s.dificuldade); campo("CD base", s.cd); campo("Sucessos", s.alvo_progresso);
    campo("Perícias", Array.isArray(s.pericias) ? s.pericias.join(", ") : "");
  }
  campo("Recompensa", s.recompensa);
  (Array.isArray(s.temas) ? s.temas : []).forEach(t => $("temasPrevia").append(no("span", "etiqueta", t)));
  const titulo = texto(s.nome).length, descricao = texto(s.descricao).length;
  $("limitesTexto").textContent = `Título ${titulo}/${C.limites.titulo} · Texto ${descricao}/${C.limites.descricao}`;
  $("limitesTexto").style.color = titulo > C.limites.titulo || descricao > C.limites.descricao ? "var(--bad)" : "";
}

function atualizar() {
  listar(); previa(); contas();
  const tema = $("fTemaSim").value;
  preencher("fTemaSim", [["", "Padrão"], ...Object.keys(objeto(sala()?.monstros_por_tema) ? sala().monstros_por_tema : {})], tema);
  desatualizar(); controles();
  if (lugar === "Dungeon") agendarPool();
  if (lugar === "Inspecao") inspecionar();
}
function desatualizar() {
  $("medidaDesatualizada").hidden = !medidaContexto || medidaContexto === contexto();
  controles();
}
function alterado() {
  revisao++; pedidoConferir++; pedidoPool++;
  $("saidaSala").hidden = true; $("saidaBanco").hidden = true;
  atualizar(); guardar(); agendarConferencia();
}
function carregar(chave) {
  origem = chave;
  const salvo = lerLocal(chave), original = originais[chave];
  const restauravel = salvo && objeto(salvo.banco) && Array.isArray(salvo.banco.salas) && salvo.banco.salas.every(objeto);
  banco = copiar(restauravel ? salvo.banco : original.banco);
  arquivo = restauravel ? salvo.arquivo : original.arquivo;
  const guardado = restauravel ? Math.max(-1, Math.min(salvo.indice ?? -1, banco.salas.length - 1)) : -1;
  revisao++; sequencia++; pedidoConferir++; pedidoPool++;
  selecao.Teste = -1; selecao.Combate = -1;
  // Reabrir o rascunho tem de cair no lugar onde a sala vive, senão o autor
  // volta num lugar que não mostra a sala que ele estava escrevendo.
  if (guardado >= 0) {
    bancadaEm = lugarDoTipo(banco.salas[guardado].tipo);
    selecao[bancadaEm] = guardado;
  }
  $("fBanco").value = chave; $("fBusca").value = "";
  $("saidaBanco").hidden = true; $("saidaSala").hidden = true;
  listarIncursoes();
  entrar(lugar === "Dungeon" || lugar === "Inspecao" ? lugar : bancadaEm);
  guardar(); agendarConferencia();
  if (restauravel) aviso("Rascunho restaurado.");
}
function agendarConferencia() {
  clearTimeout(timerConferir);
  timerConferir = setTimeout(() => conferir(false), 650);
}
async function conferir(inteiro = false) {
  if (!banco) return;
  if (!inteiro && !sala()) return;
  const id = ++pedidoConferir, versao = revisao, fonte = origem, alvo = inteiro ? "saidaBanco" : "saidaSala";
  try {
    const r = await api("/api/conferir", {dados: inteiro ? banco : sala()});
    if (id === pedidoConferir && versao === revisao && fonte === origem) recados(alvo, r, inteiro ? "Banco conferido." : "Sala conferida.");
  } catch (erro) {
    if (id === pedidoConferir) recados(alvo, {erro: erro.message});
  }
}
function novoId() {
  const ids = new Set(banco.salas.map(s => s.id));
  const modelo = banco.salas.map(s => texto(s.id).match(/^(.*?)(\d+)$/)).find(Boolean);
  const prefixo = modelo ? modelo[1] : "SALA_", largura = modelo ? modelo[2].length : 2;
  let numero = 1;
  while (ids.has(prefixo + String(numero).padStart(largura, "0"))) numero++;
  return prefixo + String(numero).padStart(largura, "0");
}
function emBranco() {
  const tipo = tipoNovo(bancadaEm === "Combate" ? "combate" : "teste") || C.tipos[0];
  const nova = {id: "", nome: "Nova sala", tipo, descricao: "", temas: []};
  if (familia(tipo) === "combate") nova.monstros = [];
  else Object.assign(nova, {dificuldade: C.dificuldades[1], cd: 13, alvo_progresso: 3, pericias: []});
  return nova;
}
function adicionar(duplicar = false) {
  if (!pronto()) return;
  if (duplicar && !sala()) return;
  const nova = duplicar ? copiar(sala()) : emBranco();
  nova.id = novoId();
  if (duplicar) nova.nome = `${texto(nova.nome)} (cópia)`;
  banco.salas.push(nova);
  indice = banco.salas.length - 1;
  selecao[lugarDoTipo(nova.tipo)] = indice;
  $("fBusca").value = "";
  if (lugarDoTipo(nova.tipo) !== bancadaEm) entrar(lugarDoTipo(nova.tipo));
  mostrarEditor(); alterado(); $("fId").focus();
}
/* Campo que não pertence ao tipo novo sai: o validador recusa sala de
   Combate com perícia e sala de teste com criatura, e o autor não tem como
   ver o resto na tela para apagar à mão. */
function trocarTipo(s, tipo) {
  s.tipo = tipo;
  const fam = familia(tipo);
  if (fam !== "teste") { s.dificuldade = null; s.cd = null; s.alvo_progresso = null; s.pericias = []; }
  else s.dificuldade ||= C.dificuldades[1];
  if (fam !== "combate") { delete s.monstros; delete s.monstros_por_tier; delete s.monstros_por_tema; }
  linhasAtuais = null; linhasDoIndice = -1;
}
function virar() {
  const s = sala();
  if (!s) return;
  const destino = tipoNovo(bancadaEm === "Combate" ? "teste" : "combate");
  if (!destino) return;
  trocarTipo(s, destino);
  selecao[lugarDoTipo(destino)] = indice;
  entrar(lugarDoTipo(destino));
  alterado();
  aviso(`“${texto(s.nome)}” agora é ${destino}.`);
}
function baixar() {
  if (!pronto()) return;
  const url = URL.createObjectURL(new Blob([bonito(banco) + "\n"], {type: "application/json"}));
  const link = no("a"); link.href = url; link.download = arquivo || "banco.json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  aviso("JSON do banco baixado.");
}

/* ------------------------------------------------------ medir e sugerir */

function parametros() {
  for (const id of ["fNivel", "fReps", "fSemente"]) {
    if (!$(id).checkValidity()) { $(id).reportValidity(); return null; }
  }
  const p = {tier: Number($("fTierSim").value), classe: $("fClasse").value, nivel: Number($("fNivel").value)};
  if ($("fSemente").value !== "") p.semente = Number($("fSemente").value);
  return p;
}
function barra(grupo, taxa) {
  const n = no("div", "taxa-linha"), trilha = no("div", "trilha"), preenchimento = no("span", taxa < .45 ? "duro" : taxa < .8 ? "medio" : "");
  preenchimento.style.width = `${Math.max(0, Math.min(100, taxa * 100))}%`;
  trilha.append(preenchimento); trilha.setAttribute("aria-hidden", "true");
  n.append(no("span", "", `${grupo} jogadores`), trilha, no("b", "", taxa == null ? "—" : `${Math.round(taxa * 100)}%`));
  return n;
}
function conta(rotulo, valor) {
  const n = no("div", "conta-linha"); n.append(no("span", "", rotulo), no("b", "", valor)); $("contaMedida").append(n);
}
async function medir() {
  if (!pronto()) return;
  const p = parametros(); if (!p) return;
  const grupos = [...document.querySelectorAll('[name="grupo"]:checked')].map(n => Number(n.value));
  if (!grupos.length) { aviso("Escolha pelo menos um tamanho de grupo."); return; }
  const atual = contexto(), nome = sala().nome;
  medindo = true; controles(); $("btMedir").textContent = "Medindo…"; $("saidaMedida").hidden = true;
  try {
    const r = await api("/api/simular", {...p, sala: sala(), tema: $("fTemaSim").value || null, grupos, repeticoes: Number($("fReps").value)});
    if (atual !== contexto()) { aviso("A sala ou os parâmetros mudaram. Meça novamente."); return; }
    if (r.erro) { recados("saidaMedida", r); return; }
    medidaContexto = atual;
    $("tituloMedida").textContent = `${texto(nome)} · Tier ${r.tier} · ${r.repeticoes} repetições`;
    $("barrasMedida").className = ""; $("barrasMedida").replaceChildren(...r.medidas.map(m => barra(m.grupo, m.taxa)));
    $("contaMedida").replaceChildren();
    r.medidas.forEach(m => conta(`Grupo de ${m.grupo}`, `${m.rodadas == null ? "—" : m.rodadas.toFixed(1)} rodadas · ${m.caidos.toFixed(1)} caídos`));
    conta("Classe / nível", `${r.classe} / ${r.nivel}`); conta("Semente", r.semente);
    conta("Criaturas", r.criaturas.map(m => m.nome).join(", "));
  } catch (erro) { if (atual === contexto()) recados("saidaMedida", {erro: erro.message}); }
  finally { medindo = false; $("btMedir").textContent = "Medir combate"; desatualizar(); }
}
async function sugerir() {
  if (!pronto()) return;
  const p = parametros(); if (!p) return;
  const atual = contexto(), tema = $("fTemaSim").value, opcoes = [$("fAmb").value, $("fBicho").value, $("fDifCombate").value];
  sugerindo = true; controles(); $("recadoSugerir").textContent = "Simulando candidatos…";
  $("sugestoes").replaceChildren(); $("saidaSugerir").hidden = true;
  try {
    const r = await api("/api/sugerir", {...p, ambiente: opcoes[0], tipo: opcoes[1], dificuldade: opcoes[2], quantas: 2});
    if (atual !== contexto() || opcoes.join() !== [$("fAmb").value, $("fBicho").value, $("fDifCombate").value].join()) {
      aviso("Os parâmetros mudaram. Gere novas sugestões."); return;
    }
    if (r.erro) { recados("saidaSugerir", r); return; }
    sugestaoContexto = atual;
    $("recadoSugerir").textContent = `Semente ${r.semente} · ${r.candidatas_no_bestiario} criaturas no filtro`;
    (r.sugestoes || []).forEach((s, i) => {
      const card = no("article", "sugestao"), lista = no("ul");
      card.append(no("h4", "", `Opção ${i + 1} · ${s.na_faixa ? "Na faixa" : "Fora da faixa"}`));
      s.bando.forEach(m => lista.append(no("li", "", `${m.quantidade}× ${m.nome}`))); card.append(lista);
      Object.entries(s.por_grupo).forEach(([grupo, taxa]) => card.append(barra(grupo, taxa)));
      const botao = no("button", "botao usar-sugestao", "Usar neste tier"); botao.type = "button";
      botao.addEventListener("click", () => {
        if (!pronto() || contexto() !== atual) { aviso("Gere sugestões para a sala atual."); return; }
        const alvo = sala();
        if (tema) {
          if (!objeto(alvo.monstros_por_tema)) alvo.monstros_por_tema = {};
          if (!objeto(alvo.monstros_por_tema[tema])) alvo.monstros_por_tema[tema] = {};
        } else if (!objeto(alvo.monstros_por_tier)) alvo.monstros_por_tier = {};
        const tiers = tema ? alvo.monstros_por_tema[tema] : alvo.monstros_por_tier;
        tiers[String(p.tier)] = s.bando.map(m => ({nome: m.nome, quantidade: m.quantidade}));
        linhasAtuais = null; linhasDoIndice = -1;
        mostrarEditor(); alterado(); aviso(`Criaturas aplicadas ao tier ${p.tier}${tema ? ` (${tema})` : ""}.`);
      });
      card.append(botao); $("sugestoes").append(card);
    });
    if (r.nenhuma_na_faixa) recados("saidaSugerir", {avisos: ["Nenhuma opção chegou à faixa pedida. Confira as taxas antes de usar."]});
  } catch (erro) { if (atual === contexto()) recados("saidaSugerir", {erro: erro.message}); }
  finally { sugerindo = false; if ($("recadoSugerir").textContent === "Simulando candidatos…") $("recadoSugerir").textContent = ""; controles(); }
}

/* ------------------------------------------------------- montar dungeon */

/* As fichas do filtro são lidas por `#fichasFiltro`, e não por `.ficha`: a
   mesma classe desenha os temas e as perícias DA SALA, e varrer a página
   inteira mandava o tema da sala aberta para dentro do filtro da dungeon. */
function fichasDoFiltro() { return [...document.querySelectorAll("#fichasFiltro .ficha")]; }
function filtro() {
  const ids = id => [...new Set($(id).value.split(",").map(s => s.trim()).filter(Boolean))];
  const f = {}, incluir = ids("fIncluir"), excluir = ids("fExcluir");
  const temas = fichasDoFiltro().filter(n => n.getAttribute("aria-pressed") === "true").map(n => n.dataset.tema);
  if (incluir.length) f.incluir = incluir;
  else if (temas.length) f.temas = temas;
  if (excluir.length) f.excluir = excluir;
  return f;
}
function limparPool(mensagem) {
  $("tabelaPool").replaceChildren(); $("contaPool").textContent = mensagem;
  $("barraPool").value = 0; $("contaFiltro").textContent = ""; $("selo").textContent = "";
  $("contaPoolAtalho").textContent = "—";
  $("saidaFiltro").hidden = true;
}
function agendarPool() {
  clearTimeout(timerPool); pedidoPool++;
  timerPool = setTimeout(conferirPool, 250);
}
async function conferirPool() {
  const f = filtro(), temIds = !!f.incluir;
  fichasDoFiltro().forEach(n => { n.disabled = temIds; });
  $("notaFiltro").textContent = temIds ? "IDs definidos: os temas não entram no filtro." : "Sem temas ou IDs, usa o banco inteiro.";
  const t = C.tamanhos[$("fTam").value];
  $("notaTamanho").textContent = t ? `${t.paradas} paradas · ${t.terminar} salas para terminar` : "";
  if (!banco) { limparPool("Abra um banco para conferir o filtro."); return; }
  const id = ++pedidoPool;
  try {
    const r = await api("/api/pool", {organizacao: banco.organizacao, tamanho: $("fTam").value, filtro: f, salas: banco.salas});
    if (id !== pedidoPool) return;
    if (r.erro) { limparPool("Não foi possível conferir."); recados("saidaFiltro", r); return; }
    $("contaPool").textContent = `${r.pool.length} salas disponíveis`;
    $("contaPoolAtalho").textContent = r.pool.length;
    $("barraPool").max = Math.max(1, r.sorteaveis); $("barraPool").value = r.pool.length;
    $("contaFiltro").textContent = `${r.pool.length} de ${r.sorteaveis} salas · Precisa de ${r.terminar} para terminar e ${r.folga} para manter ${C.limites.opcoes_por_passo} opções.`;
    $("selo").textContent = r.problemas.length ? "Insuficiente" : r.avisos.length ? "Pouca variedade" : "Suficiente";
    recados("saidaFiltro", r, "Filtro conferido.");
    $("tabelaPool").replaceChildren(...r.pool.map(s => {
      const tr = no("tr"), nome = no("td"); nome.append(no("small", "", s.id), no("span", "", s.nome));
      tr.append(nome, no("td", "", s.tipo), no("td", "", s.temas.join(", "))); return tr;
    }));
  } catch (erro) { if (id === pedidoPool) { limparPool("Não foi possível conferir."); recados("saidaFiltro", {erro: erro.message}); } }
}
/* Partir de uma incursão que já existe: o filtro dela entra nos campos para
   o autor ver o pool que ela monta hoje — e mexer a partir dali. Só as da
   Organização aberta: filtro de outra organização aponta para IDs que este
   banco não tem, e o pool sairia vazio sem dizer por quê. */
function listarIncursoes() {
  if (!C || !banco) return;
  preencher("fIncursao", [["", "Começar do zero"], ...Object.values(C.incursoes || {})
    .filter(i => i.organizacao === banco.organizacao)
    .map(i => [i.id, `${i.nome} · ${i.tamanho}`])]);
}
function carregarIncursao() {
  const alvo = C.incursoes[$("fIncursao").value];
  if (!alvo) return;
  const f = alvo.filtro || {};
  $("fTam").value = C.tamanhos[alvo.tamanho] ? alvo.tamanho : $("fTam").value;
  $("fIncluir").value = (f.incluir || []).join(", ");
  $("fExcluir").value = (f.excluir || []).join(", ");
  const pedidos = new Set(f.temas || []);
  fichasDoFiltro().forEach(n => n.setAttribute("aria-pressed", pedidos.has(n.dataset.tema)));
  agendarPool();
  aviso(`Filtro de “${texto(alvo.nome)}” carregado.`);
}
async function copiarFiltro() {
  if (!pronto()) return;
  const conteudo = bonito({filtro: filtro()});
  try { await navigator.clipboard.writeText(conteudo); aviso("Filtro JSON copiado."); }
  catch { aviso("Não foi possível copiar. Permita o acesso à área de transferência no navegador."); }
}
async function importar(evento) {
  const entrada = evento.target.files[0]; evento.target.value = "";
  if (!entrada || !pronto()) return;
  const versao = sequencia;
  try {
    const dados = JSON.parse(await entrada.text()); estrutura(dados, true);
    if (versao !== sequencia) { aviso("O banco mudou durante a abertura. Abra o arquivo novamente."); return; }
    guardar();
    const chave = `importado.${Date.now()}.${entrada.name}`;
    originais[chave] = {banco: dados, arquivo: entrada.name};
    const opcao = no("option", "", `${dados.organizacao} · ${entrada.name}`); opcao.value = chave; $("fBanco").append(opcao);
    carregar(chave); aviso("JSON aberto. O arquivo original permanece no disco.");
  } catch (erro) { aviso(`Não foi possível abrir: ${erro.message}`); }
}

async function iniciar() {
  try {
    C = await api("/api/conteudo");
    (C.tipos_de_sala || []).forEach(t => {
      FAMILIA[t.id] = t.familia; RESUMO[t.id] = t.resumo; DESCONTO[t.id] = t.desconto_cd || 0;
    });
    // O subtítulo de cada lugar sai dos tipos do servidor: tipo novo no bot
    // aparece no cartão sem ninguém reescrever a página.
    const daFamilia = f => C.tipos.filter(t => familia(t) === f);
    $("subTeste").textContent = daFamilia("teste").join(", ");
    $("subCombate").textContent = "Criaturas, medição e sugestão de bando";
    Object.entries(C.bancos).forEach(([nome, b]) => { originais[nome] = {banco: b.original || {organizacao: b.organizacao, salas: b.salas}, arquivo: b.arquivo}; });
    preencher("fBanco", Object.keys(C.bancos)); $("fBanco").disabled = false;
    preencher("fTierSim", Array.from({length: C.limites.tier_maximo}, (_, i) => i + 1), 2);
    preencher("fClasse", C.classes, "guerreiro");
    preencher("fAmb", [["", "Qualquer ambiente"], ...C.ambientes]);
    preencher("fBicho", [["", "Qualquer tipo"], ...C.tipos_de_bicho.map(t => [t.id, `${t.id} (${t.quantas})`])]);
    // As 385 do bestiario no campo de criatura: o autor escolhe da lista em
    // vez de digitar, e nome digitado errado vira sala sem criatura.
    const nomes = $("listaCriaturas");
    nomes.replaceChildren();
    (C.criaturas || []).forEach(nome => {
      const o = document.createElement("option");
      o.value = nome;
      nomes.append(o);
    });
    preencher("fDifCombate", Object.keys(C.dificuldades_de_combate).map(d => [d, `${d} · ${C.dificuldades_de_combate[d].map(v => Math.round(v * 100)).join("–")}% de vitória`]), "media");
    preencher("fTam", Object.keys(C.tamanhos));
    C.temas.forEach(t => {
      const ficha = no("button", "ficha", t); ficha.type = "button"; ficha.dataset.tema = t; ficha.setAttribute("aria-pressed", "false");
      ficha.addEventListener("click", () => { ficha.setAttribute("aria-pressed", ficha.getAttribute("aria-pressed") !== "true"); agendarPool(); });
      $("fichasFiltro").append(ficha);
    });
    let ultimo = lerLocal("ultimo");
    if (typeof ultimo === "string" && ultimo.startsWith("importado.")) {
      const salvo = lerLocal(ultimo);
      if (salvo?.original && objeto(salvo.original.banco)) {
        originais[ultimo] = salvo.original;
        const opcao = no("option", "", `${salvo.original.banco.organizacao} · ${salvo.original.arquivo}`); opcao.value = ultimo; $("fBanco").append(opcao);
      }
    }
    if (!originais[ultimo]) ultimo = Object.keys(originais)[0];
    if (ultimo) carregar(ultimo);
    else throw new Error("Nenhum banco disponível. Confira data/bancos e reinicie o estúdio.");
    if (C.problemas.length) recados("erroInicial", {avisos: C.problemas});
  } catch (erro) { recados("erroInicial", {erro: erro.message}); $("estado").textContent = "Não foi possível carregar"; }
}

/* Cada campo escreve o seu pedaco no objeto. O `id` e o `tipo` redesenham o
   formulario, porque mudam o que ele mostra. */
lerCampo("fNome", s => { s.nome = $("fNome").value; });
lerCampo("fDesc", s => { s.descricao = $("fDesc").value; });
lerCampo("fPontos", s => { s.pontos_organizacao = numero("fPontos") ?? 0; });
lerCampo("fCd", s => { s.cd = numero("fCd"); });
lerCampo("fAlvo", s => { s.alvo_progresso = numero("fAlvo"); });
lerCampo("fRecompensa", s => { s.recompensa = $("fRecompensa").value.trim() || null; });
lerCampo("fImagem", s => { s.imagem = $("fImagem").value.trim() || null; });
lerCampo("fId", s => { s.id = $("fId").value.trim(); listar(); });
$("fDif").addEventListener("change", () => {
  const s = sala(); if (!s) return;
  s.dificuldade = $("fDif").value; alterado();
});
$("fTipo").addEventListener("change", () => {
  const s = sala(); if (!s) return;
  trocarTipo(s, $("fTipo").value);
  mostrarEditor(); alterado();
});
$("btNovaCriatura").addEventListener("click", () => {
  const s = sala(); if (!s) return;
  if (linhasAtuais === null || linhasDoIndice !== indice) {
    linhasAtuais = linhasDaSala(s); linhasDoIndice = indice;
  }
  linhasAtuais.push({nome: "", quantidade: 1, tier: "", tema: ""});
  desenharCriaturas(); alterado();
});
$("fBanco").addEventListener("change", evento => {
  const destino = evento.target.value;
  if (!pronto()) { evento.target.value = origem; return; }
  guardar(); carregar(destino);
});
$("fBusca").addEventListener("input", () => { if (banco) listar(); });
$("fBuscaInspecao").addEventListener("input", () => { if (banco) inspecionar(); });
$("btAbrir").addEventListener("click", () => { if (pronto()) $("fArquivo").click(); });
$("fArquivo").addEventListener("change", importar);
$("btBaixar").addEventListener("click", baixar);
$("btConferir").addEventListener("click", () => { if (pronto()) conferir(); });
$("btConferirBanco").addEventListener("click", () => { if (pronto()) conferir(true); });
$("btNova").addEventListener("click", () => adicionar());
$("btDuplicar").addEventListener("click", () => adicionar(true));
$("btVirar").addEventListener("click", virar);
$("btExcluir").addEventListener("click", () => {
  if (!pronto() || !sala() || !confirm(`Excluir “${texto(sala().nome)}” do rascunho?`)) return;
  banco.salas.splice(indice, 1);
  // Todo índice depois do removido andou um: guardar os antigos abriria a
  // sala errada. O do lugar atual vira a vizinha, e `entrar` confere.
  selecao.Teste = -1; selecao.Combate = -1;
  selecao[bancadaEm] = Math.min(indice, banco.salas.length - 1);
  indice = -1;
  entrar(bancadaEm); alterado();
});
$("btRecarregar").addEventListener("click", () => {
  if (!banco || !confirm("Descartar o rascunho deste banco e restaurar o JSON original?")) return;
  const original = originais[origem];
  banco = copiar(original.banco); arquivo = original.arquivo;
  selecao.Teste = -1; selecao.Combate = -1; indice = -1;
  entrar(bancadaEm); alterado(); aviso("JSON original restaurado.");
});
const cartoes = [...document.querySelectorAll("[data-lugar]")];
cartoes.forEach((n, i) => {
  n.addEventListener("click", () => entrar(n.dataset.lugar));
  n.addEventListener("keydown", evento => {
    const destinos = {ArrowRight: (i + 1) % cartoes.length, ArrowLeft: (i + cartoes.length - 1) % cartoes.length, Home: 0, End: cartoes.length - 1};
    if (destinos[evento.key] !== undefined) { evento.preventDefault(); entrar(cartoes[destinos[evento.key]].dataset.lugar, true); }
  });
});
$("fTierSim").addEventListener("change", () => { $("fNivel").value = Math.min(10, Number($("fTierSim").value) * 2); desatualizar(); });
["fTemaSim", "fClasse", "fNivel", "fReps", "fSemente"].forEach(id => $(id).addEventListener("input", desatualizar));
document.querySelectorAll('[name="grupo"]').forEach(n => n.addEventListener("change", desatualizar));
["fAmb", "fBicho", "fDifCombate"].forEach(id => $(id).addEventListener("change", () => { sugestaoContexto = null; controles(); }));
$("btMedir").addEventListener("click", medir);
$("btSugerir").addEventListener("click", sugerir);
["fTam", "fIncluir", "fExcluir"].forEach(id => $(id).addEventListener("input", agendarPool));
$("fIncursao").addEventListener("change", carregarIncursao);
$("btCopiarFiltro").addEventListener("click", copiarFiltro);
document.addEventListener("keydown", evento => {
  if (!(evento.ctrlKey || evento.metaKey)) return;
  if (evento.key.toLowerCase() === "s") { evento.preventDefault(); baixar(); }
  if (evento.key === "Enter") { evento.preventDefault(); if (pronto()) conferir(); }
});
window.addEventListener("beforeunload", guardar);
// A bancada entra no lugar antes do primeiro pintar: ela mora no fim do HTML
// e apareceria sob os paineis durante o `await` do conteúdo.
$("ancoraTeste").append($("bancada"));
controles();
iniciar();
