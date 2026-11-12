"use strict";

const $ = id => document.getElementById(id);
const copiar = valor => JSON.parse(JSON.stringify(valor));
const objeto = valor => valor !== null && typeof valor === "object" && !Array.isArray(valor);
const texto = valor => valor == null ? "" : String(valor);
const bonito = valor => JSON.stringify(valor, null, 2);
const normalizar = valor => texto(valor).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const ns = "incursoes.estudio.v2.";
let C, banco, origem, arquivo, indice = 0;
// As linhas da tabela de criaturas, enquanto a sala esta aberta.
let linhasAtuais = null, linhasDoIndice = -1;
let originais = {}, sequencia = 0, revisao = 0, medindo = false, sugerindo = false;
let medidaContexto, sugestaoContexto, timerEdicao, timerPool, timerConferir, timerToast;
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
  const campo = $(id);
  campo.replaceChildren();
  itens.forEach(item => {
    const [valor, rotulo] = Array.isArray(item) ? item : [item, item];
    const opcao = no("option", "", rotulo); opcao.value = valor; campo.append(opcao);
  });
  if ([...campo.options].some(o => o.value === texto(escolhido))) campo.value = texto(escolhido);
}
function sala() { return banco?.salas[indice]; }
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
/* A conferencia da FORMA de um arquivo aberto do disco. Saiu junto com o
   editor de JSON por engano e voltou: o formulario nao deixa o autor
   escrever um banco torto, mas `importar` abre o que vier, e sem isto um
   arquivo qualquer virava `banco` e quebrava a tela em vez de avisar. */
function estrutura(dados, bancoInteiro) {
  if (!objeto(dados)) throw new Error("Use um objeto JSON entre { e }.");
  if (bancoInteiro && (typeof dados.organizacao !== "string" || !Array.isArray(dados.salas) || !dados.salas.every(objeto))) {
    throw new Error('O banco precisa de "organizacao" e de uma lista "salas" com objetos.');
  }
}

const SEM_TESTE = new Set(["Combate", "Descanso"]);

function temTeste(tipo) { return !SEM_TESTE.has(tipo); }

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

function contarBando() {
  // Linha sem nome nao conta: ela e um campo em branco esperando o autor, e
  // `montarMonstros` tambem a ignora ao escrever no objeto.
  const linhas = (linhasAtuais || []).filter(l => texto(l.nome).trim());
  const total = linhas.reduce((n, l) => n + Math.max(1, Number(l.quantidade) || 1), 0);
  $("recadoCriaturas").textContent = linhas.length
    ? `${total} criatura(s) no bando${total > C.limites.inimigos ? ` — o máximo é ${C.limites.inimigos}` : ""}.`
    : "Sala de Combate sem criatura não passa na validação.";
  $("recadoCriaturas").classList.toggle("invalido", total > C.limites.inimigos);
}

function gravarLinhas(linhas) {
  const s = sala();
  if (!s) return;
  montarMonstros(s, linhas);
  contarBando();
  alterado();
}

function preencherSelect(alvo, pares, escolhido) {
  alvo.replaceChildren();
  pares.forEach(([valor, rotulo]) => {
    const o = document.createElement("option");
    o.value = valor; o.textContent = rotulo;
    if (valor === escolhido) o.selected = true;
    alvo.append(o);
  });
}

function mostrarEditor() {
  const s = sala();
  if (linhasDoIndice !== indice) { linhasAtuais = null; linhasDoIndice = -1; }
  const form = $("formSala");
  form.hidden = !s;
  if (!s) { previa(); controles(); return; }

  $("fId").value = texto(s.id);
  $("fNome").value = texto(s.nome);
  $("fDesc").value = texto(s.descricao);
  $("fPontos").value = s.pontos_organizacao ?? 0;
  $("fRecompensa").value = texto(s.recompensa);
  $("fImagem").value = texto(s.imagem);
  preencherSelect($("fTipo"), C.tipos.filter(t => t !== "Descanso").map(t => [t, t]), s.tipo);
  preencherSelect($("fDif"), C.dificuldades.map(d => [d, d]), texto(s.dificuldade) || C.dificuldades[1]);
  $("fCd").value = s.cd ?? "";
  $("fAlvo").value = s.alvo_progresso ?? "";

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
  const combate = s.tipo === "Combate";
  $("blocoTeste").hidden = !temTeste(s.tipo);
  $("blocoCriaturas").hidden = !combate;
  if (combate) desenharCriaturas();
  previa(); controles();
}

/* O formulario escreve direto no objeto, campo a campo. Nao ha "aplicar":
   o que esta na tela e o que esta no banco, sempre — era o `aplicarEdicao`
   do JSON que podia divergir enquanto o texto estivesse pela metade. */
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

function pronto() {
  // Era o portao do JSON pela metade. Com formulario nao ha estado invalido
  // de sintaxe: ou ha banco aberto, ou nao ha.
  return !!banco;
}
function controles() {
  const temSala = !!sala(), pode = !!banco;
  ["btBaixar", "btConferirBanco", "btNova", "btCopiarFiltro"].forEach(id => { $(id).disabled = !pode; });
  ["btDuplicar", "btExcluir", "btConferir"].forEach(id => { $(id).disabled = !pode || !temSala; });
  $("btRecarregar").disabled = !banco;
  const combate = temSala && sala().tipo === "Combate";
  $("avisoCombate").hidden = combate;
  $("btMedir").disabled = !pode || !combate || medindo;
  $("btSugerir").disabled = !pode || !combate || sugerindo;
  document.querySelectorAll(".usar-sugestao").forEach(n => { n.disabled = !pode || sugestaoContexto !== contexto(); });
}
function listar() {
  const busca = normalizar($("fBusca").value), lista = $("listaSalas");
  lista.replaceChildren();
  banco.salas.forEach((s, i) => {
    if (!normalizar(`${texto(s.id)} ${texto(s.nome)}`).includes(busca)) return;
    const botao = no("button", "sala-btn"); botao.type = "button";
    botao.setAttribute("aria-current", i === indice ? "true" : "false");
    botao.append(no("span", "snome", s.nome || "Sem nome"));
    const meta = no("span", "sala-meta");
    meta.append(no("span", "sid", s.id || "Sem ID"), no("span", "", s.tipo || "Sem tipo"));
    botao.append(meta);
    botao.addEventListener("click", () => {
      if (!pronto()) return;
      indice = i; mostrarEditor(); atualizar(); guardar(); agendarConferencia();
    });
    const item = no("li"); item.append(botao); lista.append(item);
  });
  $("contaSalas").textContent = banco.salas.length;
  $("listaVazia").hidden = lista.children.length > 0;
  $("notaDescanso").textContent = banco.salas.some(s => s.tipo === "Descanso") ? "Descanso aparece nas paradas fixas." : "Sem sala de Descanso.";
}
function previa() {
  const s = sala();
  $("nomeSala").textContent = s?.nome || "Selecione uma sala";
  $("tipoSala").textContent = s?.tipo || "Sala";
  $("tipoSala").classList.toggle("combate", s?.tipo === "Combate");
  $("idSala").textContent = texto(s?.id);
  $("dTitulo").textContent = s?.nome || "Sua sala aparece aqui";
  $("dCorpo").textContent = texto(s?.descricao);
  $("dCampos").replaceChildren(); $("temasPrevia").replaceChildren();
  if (!s) { $("limitesTexto").textContent = ""; return; }
  function campo(nome, valor) {
    if (valor == null || valor === "") return;
    const n = no("div"); n.append(no("strong", "", nome), no("span", "", valor)); $("dCampos").append(n);
  }
  if (s.tipo === "Combate") {
    const tiers = objeto(s.monstros_por_tier) ? Object.keys(s.monstros_por_tier) : [];
    campo("Criaturas", tiers.length ? `Tiers ${tiers.join(", ")}` : Array.isArray(s.monstros) ? s.monstros.map(m => `${m.quantidade || 1}× ${texto(m.nome)}`).join(", ") : "Não definidas");
    campo("Variantes", objeto(s.monstros_por_tema) ? Object.keys(s.monstros_por_tema).join(", ") : "");
  } else if (s.tipo !== "Descanso") {
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
  listar(); previa();
  const tema = $("fTemaSim").value;
  preencher("fTemaSim", [["", "Padrão"], ...Object.keys(objeto(sala()?.monstros_por_tema) ? sala().monstros_por_tema : {})], tema);
  desatualizar(); controles();
  if (!$("painelFiltro").hidden) agendarPool();
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
  indice = restauravel ? Math.max(0, Math.min(salvo.indice || 0, banco.salas.length - 1)) : 0;
  revisao++; sequencia++; pedidoConferir++; pedidoPool++;
  $("fBanco").value = chave; $("fBusca").value = "";
  $("saidaBanco").hidden = true; $("saidaSala").hidden = true;
  mostrarEditor(); atualizar();
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
function aba(nome, foco = false) {
  document.querySelectorAll("[data-aba]").forEach(n => {
    const ativa = n.dataset.aba === nome;
    n.setAttribute("aria-selected", ativa); n.tabIndex = ativa ? 0 : -1;
    $("painel" + n.dataset.aba).hidden = !ativa;
    if (ativa && foco) n.focus();
  });
  if (nome === "Filtro") agendarPool();
}
function novoId() {
  const ids = new Set(banco.salas.map(s => s.id));
  const modelo = banco.salas.map(s => texto(s.id).match(/^(.*?)(\d+)$/)).find(Boolean);
  const prefixo = modelo ? modelo[1] : "SALA_", largura = modelo ? modelo[2].length : 2;
  let numero = 1;
  while (ids.has(prefixo + String(numero).padStart(largura, "0"))) numero++;
  return prefixo + String(numero).padStart(largura, "0");
}
function adicionar(duplicar = false) {
  if (!pronto()) return;
  const nova = duplicar ? copiar(sala()) : {id: "", nome: "Nova sala", tipo: "Evento", descricao: "", temas: [], dificuldade: C.dificuldades[1], cd: 13, alvo_progresso: 3, pericias: []};
  nova.id = novoId();
  if (duplicar) nova.nome = `${texto(nova.nome)} (cópia)`;
  banco.salas.push(nova); indice = banco.salas.length - 1;
  $("fBusca").value = ""; mostrarEditor(); alterado(); aba("Editar"); $("fId").focus();
}
function baixar() {
  if (!pronto()) return;
  const url = URL.createObjectURL(new Blob([bonito(banco) + "\n"], {type: "application/json"}));
  const link = no("a"); link.href = url; link.download = arquivo || "banco.json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  aviso("JSON do banco baixado.");
}
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
        mostrarEditor(); alterado(); aba("Editar"); aviso(`Criaturas aplicadas ao tier ${p.tier}${tema ? ` (${tema})` : ""}.`);
      });
      card.append(botao); $("sugestoes").append(card);
    });
    if (r.nenhuma_na_faixa) recados("saidaSugerir", {avisos: ["Nenhuma opção chegou à faixa pedida. Confira as taxas antes de usar."]});
  } catch (erro) { if (atual === contexto()) recados("saidaSugerir", {erro: erro.message}); }
  finally { sugerindo = false; if ($("recadoSugerir").textContent === "Simulando candidatos…") $("recadoSugerir").textContent = ""; controles(); }
}
function filtro() {
  const ids = id => [...new Set($(id).value.split(",").map(s => s.trim()).filter(Boolean))];
  const f = {}, incluir = ids("fIncluir"), excluir = ids("fExcluir");
  const temas = [...document.querySelectorAll('.ficha[aria-pressed="true"]')].map(n => n.dataset.tema);
  if (incluir.length) f.incluir = incluir;
  else if (temas.length) f.temas = temas;
  if (excluir.length) f.excluir = excluir;
  return f;
}
function limparPool(mensagem) {
  $("tabelaPool").replaceChildren(); $("contaPool").textContent = mensagem;
  $("barraPool").value = 0; $("contaFiltro").textContent = ""; $("selo").textContent = "";
  $("saidaFiltro").hidden = true;
}
function agendarPool() {
  clearTimeout(timerPool); pedidoPool++;
  timerPool = setTimeout(conferirPool, 250);
}
async function conferirPool() {
  const f = filtro(), temIds = !!f.incluir;
  document.querySelectorAll(".ficha").forEach(n => { n.disabled = temIds; });
  $("notaFiltro").textContent = temIds ? "IDs definidos: os temas não entram no filtro." : "Sem temas ou IDs, usa o banco inteiro.";
  if (!banco) { limparPool("Abra um banco para conferir o filtro."); return; }
  const id = ++pedidoPool;
  try {
    const r = await api("/api/pool", {organizacao: banco.organizacao, tamanho: $("fTam").value, filtro: f, salas: banco.salas});
    if (id !== pedidoPool) return;
    if (r.erro) { limparPool("Não foi possível conferir."); recados("saidaFiltro", r); return; }
    $("contaPool").textContent = `${r.pool.length} salas disponíveis`;
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
    carregar(chave); aba("Editar"); aviso("JSON aberto. O arquivo original permanece no disco.");
  } catch (erro) { aviso(`Não foi possível abrir: ${erro.message}`); }
}
async function iniciar() {
  try {
    C = await api("/api/conteudo");
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
   formulario, porque mudam o que ele mostra: trocar para Combate troca o
   bloco do teste pelo das criaturas. */
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
  s.tipo = $("fTipo").value;
  // Campo que nao pertence ao tipo novo sai: o validador recusa sala de
  // Combate com pericia e sala de teste com criatura, e o autor nao tem
  // como ver o resto na tela para apagar a mao.
  if (s.tipo === "Combate") {
    s.dificuldade = null; s.cd = null; s.alvo_progresso = null; s.pericias = [];
  } else {
    delete s.monstros; delete s.monstros_por_tier; delete s.monstros_por_tema;
    s.dificuldade ||= C.dificuldades[1];
  }
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
$("btAbrir").addEventListener("click", () => { if (pronto()) $("fArquivo").click(); });
$("fArquivo").addEventListener("change", importar);
$("btBaixar").addEventListener("click", baixar);
$("btConferir").addEventListener("click", () => { if (pronto()) conferir(); });
$("btConferirBanco").addEventListener("click", () => { if (pronto()) conferir(true); });
$("btNova").addEventListener("click", () => adicionar());
$("btDuplicar").addEventListener("click", () => adicionar(true));
$("btExcluir").addEventListener("click", () => {
  if (!pronto() || !confirm(`Excluir “${texto(sala().nome)}” do rascunho?`)) return;
  banco.salas.splice(indice, 1); indice = Math.max(0, Math.min(indice, banco.salas.length - 1));
  mostrarEditor(); alterado();
});
$("btRecarregar").addEventListener("click", () => {
  if (!banco || !confirm("Descartar o rascunho deste banco e restaurar o JSON original?")) return;
  const original = originais[origem];
  banco = copiar(original.banco); arquivo = original.arquivo; indice = 0;
  mostrarEditor(); alterado(); aviso("JSON original restaurado.");
});
const abas = [...document.querySelectorAll("[data-aba]")];
abas.forEach((n, i) => {
  n.addEventListener("click", () => aba(n.dataset.aba));
  n.addEventListener("keydown", evento => {
    const destinos = {ArrowRight: (i + 1) % abas.length, ArrowLeft: (i + abas.length - 1) % abas.length, Home: 0, End: abas.length - 1};
    if (destinos[evento.key] !== undefined) { evento.preventDefault(); aba(abas[destinos[evento.key]].dataset.aba, true); }
  });
});
$("fTierSim").addEventListener("change", () => { $("fNivel").value = Math.min(10, Number($("fTierSim").value) * 2); desatualizar(); });
["fTemaSim", "fClasse", "fNivel", "fReps", "fSemente"].forEach(id => $(id).addEventListener("input", desatualizar));
document.querySelectorAll('[name="grupo"]').forEach(n => n.addEventListener("change", desatualizar));
["fAmb", "fBicho", "fDifCombate"].forEach(id => $(id).addEventListener("change", () => { sugestaoContexto = null; controles(); }));
$("btMedir").addEventListener("click", medir);
$("btSugerir").addEventListener("click", sugerir);
["fTam", "fIncluir", "fExcluir"].forEach(id => $(id).addEventListener("input", agendarPool));
$("btCopiarFiltro").addEventListener("click", copiarFiltro);
document.addEventListener("keydown", evento => {
  if (!(evento.ctrlKey || evento.metaKey)) return;
  if (evento.key.toLowerCase() === "s") { evento.preventDefault(); baixar(); }
  if (evento.key === "Enter") { evento.preventDefault(); if (pronto()) conferir(); }
});
window.addEventListener("beforeunload", guardar);
controles();
iniciar();
