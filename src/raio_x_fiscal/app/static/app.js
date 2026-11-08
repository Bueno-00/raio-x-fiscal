/* Raio-X Fiscal: a página. Sem biblioteca de fora; todo texto que vem da nota entra como texto
   (textContent), nunca como HTML. */
(function () {
  "use strict";

  var POR_PAGINA = window.matchMedia && window.matchMedia("(max-width: 760px)").matches ? 20 : 40;
  var ROTULO = { vermelho: "Erro provável", amarelo: "Conferir", verde: "Ok" };
  var NOME_ABAS = ["notas", "cadastro", "pesquisa"];
  var S = {
    estado: null, dados: null, filtro: "todos", regra: "", empresa: "", texto: "", pagina: 0,
    arquivosNotas: [], arquivoCad: null, marcados: {}, abertos: {}
  };

  function $(id) { return document.getElementById(id); }
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k) || attrs[k] == null || attrs[k] === false) continue;
        if (k === "class") el.className = attrs[k];
        else if (k === "text") el.textContent = attrs[k];
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
        else el.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
      }
    }
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      if (Array.isArray(c)) c.forEach(function (x) { if (x != null && x !== false) el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); });
      else el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  function limpa(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function num(n) { return Number(n || 0).toLocaleString("pt-BR"); }
  function pct(a, b) { return b ? (100 * a / b).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%" : "0%"; }
  function moeda(v) { return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }

  function status(msg, tipo) {
    var el = limpa($("estado"));
    if (!msg) return;
    if (tipo === "carregando") el.appendChild(h("div", { class: "carregando" }, h("span", { class: "giro", "aria-hidden": "true" }), msg));
    else el.appendChild(h("p", { class: tipo === "erro" ? "erro" : "", style: "margin:0" }, msg));
  }

  function api(url, opcoes) {
    return fetch(url, opcoes).then(function (r) {
      var tipo = r.headers.get("content-type") || "";
      if (!r.ok) {
        if (tipo.indexOf("json") >= 0) return r.json().then(function (j) { throw new Error(j.erro || "Erro " + r.status); });
        throw new Error(r.status === 413 ? "Arquivo grande demais para um envio." : "Erro " + r.status + ". Tente de novo.");
      }
      return tipo.indexOf("json") >= 0 ? r.json() : r;
    });
  }

  function baixar(resp, nomePadrao) {
    var cd = resp.headers.get("content-disposition") || "";
    var m = /filename="([^"]+)"/.exec(cd);
    var aviso = resp.headers.get("x-raiox-avisos");
    return resp.blob().then(function (b) {
      var a = h("a", { href: URL.createObjectURL(b), download: m ? m[1] : nomePadrao });
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
      return aviso;
    });
  }

  /* ---------------- abas ---------------- */
  function abrirAba(nome) {
    NOME_ABAS.forEach(function (n) {
      var b = $("aba-" + n), p = $("p-" + n), ativo = n === nome;
      b.setAttribute("aria-selected", ativo ? "true" : "false");
      b.tabIndex = ativo ? 0 : -1;
      p.hidden = !ativo;
    });
    status("");
  }
  NOME_ABAS.forEach(function (n, i) {
    var b = $("aba-" + n);
    b.addEventListener("click", function () { abrirAba(n); });
    b.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var j = (i + (e.key === "ArrowRight" ? 1 : NOME_ABAS.length - 1)) % NOME_ABAS.length;
      abrirAba(NOME_ABAS[j]); $("aba-" + NOME_ABAS[j]).focus();
    });
  });

  /* ---------------- porta 1: notas ---------------- */
  function lerEntrada(entry, caminho, lista) {
    return new Promise(function (ok) {
      if (entry.isFile) { entry.file(function (f) { lista.push([f, caminho + f.name]); ok(); }, function () { ok(); }); return; }
      var leitor = entry.createReader(), todos = [];
      (function prox() {
        leitor.readEntries(function (es) {
          if (!es.length) Promise.all(todos.map(function (x) { return lerEntrada(x, caminho + entry.name + "/", lista); })).then(ok);
          else { todos = todos.concat(Array.prototype.slice.call(es)); prox(); }
        }, function () { ok(); });
      })();
    });
  }
  function mostraSelNotas() {
    var el = limpa($("sel-notas")), arqs = S.arquivosNotas;
    var validos = arqs.filter(function (a) { return /\.(xml|zip)$/i.test(a[1]); });
    var total = validos.reduce(function (s, a) { return s + a[0].size; }, 0);
    $("btn-notas").disabled = !validos.length;
    if (!arqs.length) { el.hidden = true; return; }
    el.hidden = false;
    var zips = validos.filter(function (a) { return /\.zip$/i.test(a[1]); }).length;
    var txt = validos.length ? num(validos.length - zips) + " XML" + (zips ? " e " + zips + " .zip" : "") + " · " + (total / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " MB" : "Nenhum .xml ou .zip na seleção";
    el.appendChild(h("span", null, h("b", { text: "Selecionado: " }), txt));
    el.appendChild(h("button", { class: "limpar", type: "button", onclick: function () { S.arquivosNotas = []; mostraSelNotas(); } }, "limpar"));
    var lim = S.estado ? S.estado.limites.envio_mb : 25;
    if (total > lim * 1048576) { status("O envio passa de " + lim + " MB. Divida em partes (por empresa, por exemplo).", "erro"); $("btn-notas").disabled = true; }
    else status("");
  }
  $("arq-notas").addEventListener("change", function (e) { S.arquivosNotas = Array.prototype.map.call(e.target.files, function (f) { return [f, f.name]; }); mostraSelNotas(); e.target.value = ""; });
  $("pasta-notas").addEventListener("change", function (e) { S.arquivosNotas = Array.prototype.map.call(e.target.files, function (f) { return [f, f.webkitRelativePath || f.name]; }); mostraSelNotas(); e.target.value = ""; });
  function zonaArrastar(zona, aoSoltar, aoClicar) {
    zona.addEventListener("dragover", function (e) { e.preventDefault(); zona.classList.add("sobre"); });
    zona.addEventListener("dragleave", function () { zona.classList.remove("sobre"); });
    zona.addEventListener("drop", function (e) { e.preventDefault(); zona.classList.remove("sobre"); aoSoltar(e.dataTransfer); });
    zona.addEventListener("click", function (e) { if (e.target.closest("label")) return; aoClicar(); });
    zona.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); aoClicar(); } });
  }
  zonaArrastar($("zona-notas"), function (dt) {
    var lista = [], ps = [];
    Array.prototype.forEach.call(dt.items || [], function (it) { var en = it.webkitGetAsEntry && it.webkitGetAsEntry(); if (en) ps.push(lerEntrada(en, "", lista)); });
    if (!ps.length) Array.prototype.forEach.call(dt.files || [], function (f) { lista.push([f, f.name]); });
    Promise.all(ps).then(function () { S.arquivosNotas = lista; mostraSelNotas(); });
  }, function () { $("arq-notas").click(); });

  function ocupado(btn, sim, texto) {
    if (!btn) return;
    if (sim) { btn.dataset.txt = btn.dataset.txt || btn.innerHTML; btn.classList.add("ocupado"); }
    else { btn.classList.remove("ocupado"); }
  }

  $("btn-notas").addEventListener("click", function () {
    var validos = S.arquivosNotas.filter(function (a) { return /\.(xml|zip)$/i.test(a[1]); });
    if (!validos.length) return;
    var fd = new FormData();
    validos.forEach(function (a) { fd.append("f", a[0], a[1]); });
    var b = $("btn-notas"); ocupado(b, true);
    status("Conferindo " + num(validos.length) + " arquivo(s)...", "carregando");
    api("/api/notas", { method: "POST", body: fd }).then(function (j) { status(""); mostrar(j); })
      .catch(function (e) { status(e.message, "erro"); }).then(function () { ocupado(b, false); });
  });
  $("btn-exemplo").addEventListener("click", function () {
    var b = $("btn-exemplo"); ocupado(b, true);
    status("Conferindo as notas de exemplo...", "carregando");
    api("/api/exemplo", { method: "POST" }).then(function (j) { status(""); mostrar(j); })
      .catch(function (e) { status(e.message, "erro"); }).then(function () { ocupado(b, false); });
  });

  /* ---------------- porta 2: cadastro ---------------- */
  function mostraSelCad() {
    var el = limpa($("sel-cad")), f = S.arquivoCad;
    $("btn-cad").disabled = !f;
    if (!f) { el.hidden = true; return; }
    el.hidden = false;
    el.appendChild(h("span", null, h("b", { text: "Selecionado: " }), f.name + " · " + (f.size / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " KB"));
    el.appendChild(h("button", { class: "limpar", type: "button", onclick: function () { S.arquivoCad = null; mostraSelCad(); } }, "limpar"));
  }
  $("arq-cad").addEventListener("change", function (e) { S.arquivoCad = e.target.files[0] || null; mostraSelCad(); e.target.value = ""; });
  zonaArrastar($("zona-cad"), function (dt) { S.arquivoCad = (dt.files && dt.files[0]) || null; mostraSelCad(); }, function () { $("arq-cad").click(); });
  function enviaCad(url, fd, btn) {
    ocupado(btn, true);
    status("Conferindo o cadastro...", "carregando");
    api(url, { method: "POST", body: fd }).then(function (j) { status(""); mostrar(j); })
      .catch(function (e) { status(e.message, "erro"); }).then(function () { ocupado(btn, false); });
  }
  $("btn-cad").addEventListener("click", function () {
    if (!S.arquivoCad) return;
    var fd = new FormData(); fd.append("f", S.arquivoCad, S.arquivoCad.name);
    enviaCad("/api/cadastro", fd, $("btn-cad"));
  });
  $("btn-cad-exemplo").addEventListener("click", function () { enviaCad("/api/cadastro/exemplo", null, $("btn-cad-exemplo")); });

  /* ---------------- porta 3: pesquisa ---------------- */
  function pesquisar(q) {
    q = (q || "").trim();
    var alvo = limpa($("res-busca"));
    if (q.length < 3) { status("Escreva pelo menos 3 letras.", "erro"); return; }
    status("Pesquisando...", "carregando");
    api("/api/pesquisar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q: q }) })
      .then(function (j) {
        status("");
        if (!j.resultados.length) { alvo.appendChild(h("p", { class: "vazio", text: "Nenhum NCM encontrado para essa descrição." })); return; }
        j.resultados.forEach(function (r, i) {
          var p = Math.round(r.confianca * 100);
          alvo.appendChild(h("div", { class: "sug" },
            h("div", null, h("div", { class: "sug-ncm", text: r.ncm_formatado }), i === 0 ? h("div", { class: "conf", text: "mais provável" }) : null),
            h("div", { class: "sug-desc", text: r.descricao_oficial }),
            h("div", { class: "sug-conf" }, h("div", { class: "medidor" }, h("i", { style: "width:" + Math.max(2, p) + "%" })), (r.confianca < 0.005 ? "menos de 1" : p) + "% de confiança")));
        });
        alvo.appendChild(h("p", { class: "nota-peq", text: "Confiança calibrada num mês que o modelo não viu. Confira a descrição oficial antes de usar o código." }));
      }).catch(function (e) { status(e.message, "erro"); });
  }
  $("form-busca").addEventListener("submit", function (e) { e.preventDefault(); pesquisar($("q").value); });
  Array.prototype.forEach.call($("chips-busca").querySelectorAll("button"), function (b) {
    b.addEventListener("click", function () { $("q").value = b.textContent; pesquisar(b.textContent); });
  });

  /* ---------------- resultado ---------------- */
  function itensFiltrados() {
    var d = S.dados; if (!d) return [];
    var t = S.texto.toLowerCase();
    return d.itens.filter(function (it) {
      if (S.filtro !== "todos" && it.semaforo !== S.filtro) return false;
      if (S.regra && it.regras.indexOf(S.regra) < 0) return false;
      if (S.empresa && it.grupo !== S.empresa) return false;
      if (t) {
        var alvo = (it.descricao + " " + it.ncm + " " + (it.ncm_sugerido || "") + " " + (it.numero || "") + " " + (it.codigo || "") + " " + (it.cfop || "")).toLowerCase();
        if (alvo.indexOf(t) < 0 && alvo.replace(/\./g, "").indexOf(t.replace(/\./g, "")) < 0) return false;
      }
      return true;
    });
  }
  function contagem(lista) {
    var c = { todos: lista.length, vermelho: 0, amarelo: 0, verde: 0 };
    lista.forEach(function (it) { c[it.semaforo]++; });
    return c;
  }

  function mostrar(j) {
    S.dados = j; S.filtro = j.resumo.vermelho || j.resumo.amarelo ? "todos" : "todos"; S.regra = ""; S.empresa = ""; S.texto = ""; S.pagina = 0; S.abertos = {};
    S.marcados = {};
    if (j.tipo === "cadastro") j.itens.forEach(function (it) { if (it.semaforo === "vermelho" && it.ncm_sugerido) S.marcados[it.linha] = true; });
    $("filtro-txt").value = "";
    $("resultado").hidden = false;
    var cad = j.tipo === "cadastro", ex = j.origem === "notas de exemplo";
    $("res-rotulo").textContent = cad ? "Resultado do cadastro" : (ex ? "Resultado das notas de exemplo" : "Resultado das notas");
    $("res-titulo").textContent = cad ? "Planilha " + j.origem : (ex ? "8 comércios fictícios, produtos reais" : "Conferência das notas enviadas");
    var r = j.resumo;
    $("res-meta").textContent = cad
      ? num(r.produtos) + " produtos · tabela NCM " + (r.tabela_ncm || "") + " · conferido agora"
      : num(r.notas) + " notas · " + num(r.itens) + " itens · tabela NCM " + r.tabela_ncm + " · conferido em " + r.gerado_em;
    renderKpis(); renderExemplo(); renderAvisos(); renderEmpresas(); renderRegras(); renderSegmentos(); renderFiltroRegra(); renderTabela(); renderBaixar(); contextoChat();
    setTimeout(function () { $("resultado").scrollIntoView({ behavior: "smooth", block: "start" }); }, 60);
  }

  function renderKpis() {
    var j = S.dados, r = j.resumo, cad = j.tipo === "cadastro", total = cad ? r.produtos : r.itens;
    var el = limpa($("kpis"));
    function kpi(cls, filtro, ponto, rot, n, sub) {
      var attrs = { class: "kpi " + cls };
      var tag = filtro ? "button" : "div";
      if (filtro) { attrs.type = "button"; attrs["aria-pressed"] = S.filtro === filtro ? "true" : "false"; attrs.onclick = function () { S.filtro = S.filtro === filtro ? "todos" : filtro; S.pagina = 0; renderSegmentos(); renderKpis(); renderTabela(); }; }
      return h(tag, attrs, h("span", { class: "kpi-rot" }, ponto ? h("span", { class: "ponto " + ponto }) : null, rot), h("span", { class: "kpi-num", text: num(n) }), h("span", { class: "kpi-sub", text: sub }));
    }
    el.appendChild(kpi("", null, null, cad ? "Produtos conferidos" : "Itens conferidos", total, cad ? "na planilha" : num(r.notas) + " notas"));
    el.appendChild(kpi("k-verm", "vermelho", "vermelho", "Erro provável", r.vermelho, pct(r.vermelho, total) + " dos itens"));
    el.appendChild(kpi("k-amar", "amarelo", "amarelo", "Conferir", r.amarelo, pct(r.amarelo, total) + " dos itens"));
    el.appendChild(kpi("k-verde", "verde", "verde", "Ok", r.verde, pct(r.verde, total) + " dos itens"));
    if (cad) el.appendChild(kpi("", null, "cinza", "Com sugestão de NCM", j.itens.filter(function (i) { return i.ncm_sugerido; }).length, "para revisar"));
    else el.appendChild(kpi("", null, "cinza", "Aceitos pelo escritório", r.aceitos_escritorio || 0, "regra do escritório"));
    var b = limpa($("barra-total"));
    ["vermelho", "amarelo", "verde"].forEach(function (k) { if (r[k]) b.appendChild(h("i", { class: k, style: "width:" + (100 * r[k] / total) + "%" })); });
  }

  function renderExemplo() {
    var el = limpa($("aviso-exemplo")), c = S.dados.conferencia;
    if (!c) { el.hidden = true; return; }
    el.hidden = false;
    el.appendChild(h("h3", { text: "Plantamos " + num(c.erros_plantados) + " erros de propósito. O Raio-X marcou " + num(c.erros_pegos) + "." }));
    el.appendChild(h("div", { class: "ex-links" },
      h("a", { class: "btn btn-sec", href: "/api/exemplo/gabarito.csv", download: "" }, "Gabarito (CSV)"),
      h("a", { class: "btn btn-sec", href: "/api/exemplo/notas.zip", download: "" }, "Notas (.zip)")));
    el.appendChild(h("p", { text: "Empresas inventadas, mas os produtos são descrições reais das notas públicas, com o NCM que aparece em 85% ou mais das vezes. " + num(c.itens_com_erro) + " dos " + num(c.itens) + " itens têm algum erro; os outros " + num(c.itens_limpos) + " estão certos (" + num(c.limpos_sem_alerta) + " ficaram verdes)." }));
    var tb = h("tbody");
    c.por_tipo.forEach(function (t) {
      tb.appendChild(h("tr", null, h("td", { text: t.o_que_e }), h("td", { class: "num", text: num(t.itens) }), h("td", { class: "num", text: num(t.pegos) })));
    });
    var det = h("details", null, h("summary", { text: "Ver por tipo de erro" }),
      h("table", { class: "tab-gab" }, h("thead", null, h("tr", null, h("th", { text: "Erro plantado" }), h("th", { text: "Itens" }), h("th", { text: "Marcados" }))), tb));
    if (c.perdidos.length) det.appendChild(h("p", { style: "margin-top:8px", text: "O que passou: " + c.perdidos.map(function (p) { return p.descricao + " (" + p.erro.toLowerCase() + ")"; }).filter(function (v, i, a) { return a.indexOf(v) === i; }).join("; ") + ". Nesses casos o modelo não teve certeza suficiente para acusar." }));
    el.appendChild(det);
    $("num-exemplo").textContent = num(c.erros_pegos) + " de " + num(c.erros_plantados);
  }

  function renderAvisos() {
    var el = limpa($("avisos")), av = S.dados.avisos || [];
    if (!av.length) { el.hidden = true; return; }
    el.hidden = false;
    el.appendChild(h("b", { text: av.length + " aviso(s) na leitura dos arquivos" }));
    var ul = h("ul"); av.slice(0, 8).forEach(function (a) { ul.appendChild(h("li", { text: a })); }); el.appendChild(ul);
  }

  function renderEmpresas() {
    var el = limpa($("empresas")), emps = S.dados.empresas || [];
    if (emps.length < 2) { el.hidden = true; return; }
    el.hidden = false;
    var todas = { grupo: "", nome: "Todas as empresas", itens: S.dados.resumo.itens, vermelho: S.dados.resumo.vermelho, amarelo: S.dados.resumo.amarelo, verde: S.dados.resumo.verde, notas: S.dados.resumo.notas };
    [todas].concat(emps).forEach(function (e) {
      var mini = h("span", { class: "emp-mini", "aria-hidden": "true" });
      ["vermelho", "amarelo", "verde"].forEach(function (k) { if (e[k]) mini.appendChild(h("i", { class: k, style: "width:" + (100 * e[k] / e.itens) + "%" })); });
      el.appendChild(h("button", { class: "emp", type: "button", "aria-pressed": S.empresa === e.grupo ? "true" : "false", title: e.nome, onclick: function () { S.empresa = e.grupo; S.pagina = 0; renderEmpresas(); renderSegmentos(); renderTabela(); renderBaixar(); } },
        h("span", { class: "emp-nome", text: e.nome }), mini,
        h("span", { class: "emp-num" }, h("span", null, h("b", { text: num(e.notas) }), " notas"), h("span", { class: "nv" }, h("b", { text: num(e.vermelho) }), " verm."), h("span", { class: "na" }, h("b", { text: num(e.amarelo) }), " amar."))));
    });
  }

  function renderSegmentos() {
    var el = limpa($("segmentos"));
    var base = S.dados.itens.filter(function (it) { return (!S.empresa || it.grupo === S.empresa) && (!S.regra || it.regras.indexOf(S.regra) >= 0); });
    var c = contagem(base);
    if (S.dados.itens_omitidos && !S.empresa && !S.regra) c.verde += S.dados.itens_omitidos;
    [["todos", "Todos", null], ["vermelho", "Erro provável", "vermelho"], ["amarelo", "Conferir", "amarelo"], ["verde", "Ok", "verde"]].forEach(function (s) {
      el.appendChild(h("button", { type: "button", "aria-pressed": S.filtro === s[0] ? "true" : "false", onclick: function () { S.filtro = s[0]; S.pagina = 0; renderSegmentos(); renderKpis(); renderTabela(); } },
        s[2] ? h("span", { class: "ponto " + s[2] }) : null, s[1], h("span", { class: "cont", text: num(s[0] === "todos" ? c.todos + (S.dados.itens_omitidos && !S.empresa && !S.regra ? S.dados.itens_omitidos : 0) : c[s[0]]) })));
    });
  }

  function renderFiltroRegra() {
    var sel = limpa($("filtro-regra")), nomes = S.dados.nomes_regras || {}, usadas = {};
    S.dados.itens.forEach(function (it) { it.regras.forEach(function (r) { usadas[r] = (usadas[r] || 0) + 1; }); });
    sel.appendChild(h("option", { value: "", text: "Todas as checagens" }));
    Object.keys(usadas).sort(function (a, b) { return usadas[b] - usadas[a]; }).forEach(function (r) { sel.appendChild(h("option", { value: r, text: (nomes[r] || r) + " (" + usadas[r] + ")" })); });
    sel.value = S.regra;
  }
  $("filtro-regra").addEventListener("change", function (e) { S.regra = e.target.value; S.pagina = 0; renderSegmentos(); renderRegras(); renderTabela(); });
  var tempoBusca;
  $("filtro-txt").addEventListener("input", function (e) { clearTimeout(tempoBusca); tempoBusca = setTimeout(function () { S.texto = e.target.value.trim(); S.pagina = 0; renderTabela(); }, 180); });

  function renderRegras() {
    var el = limpa($("regras-lista")), nomes = S.dados.nomes_regras || {};
    var lista = S.dados.por_regra;
    if (!lista) {
      var c = {};
      S.dados.itens.forEach(function (it) { it.regras.forEach(function (r) { c[r] = c[r] || { regra: r, nome: nomes[r] || r, vermelho: 0, amarelo: 0, aceitos: 0 }; c[r][it.semaforo === "vermelho" ? "vermelho" : "amarelo"]++; }); });
      lista = Object.keys(c).map(function (k) { return c[k]; }).sort(function (a, b) { return (b.vermelho - a.vermelho) || (b.amarelo - a.amarelo); });
    }
    if (!lista.length) { el.appendChild(h("li", { class: "vazio", text: "Nenhum alerta. Tudo verde." })); return; }
    lista.forEach(function (r) {
      el.appendChild(h("li", null, h("button", { type: "button", "aria-pressed": S.regra === r.regra ? "true" : "false", onclick: function () { S.regra = S.regra === r.regra ? "" : r.regra; $("filtro-regra").value = S.regra; S.pagina = 0; renderRegras(); renderSegmentos(); renderTabela(); } },
        h("span", { text: r.nome }), h("span", { class: "ns" }, r.vermelho ? h("span", { class: "nv", text: num(r.vermelho) }) : null, r.amarelo ? h("span", { class: "na", text: num(r.amarelo) }) : null, r.aceitos ? h("span", { class: "nac", title: "aceitos pela regra do escritório", text: "+" + num(r.aceitos) + " aceitos" }) : null))));
    });
  }

  function celulaNcm(cod, curta, ruim, rotulo) {
    return h("div", { class: "c-ncm" }, h("span", { class: "rot-m", text: rotulo }), h("div", { class: "cod" + (ruim ? " ruim" : ""), text: cod || "(vazio)" }), curta ? h("div", { class: "cod-desc", title: curta, text: curta }) : null);
  }
  function celulaSug(it) {
    if (!it.ncm_sugerido) return h("div", { class: "c-sug sugerido" }, h("span", { class: "rot-m", text: "Sugerido" }), h("span", { class: "vazio", text: "sem sugestão" }));
    return h("div", { class: "c-sug sugerido" }, h("span", { class: "rot-m", text: "Sugerido" }),
      h("div", { class: "cod" }, h("span", { class: "seta", "aria-hidden": "true", text: "→" }), it.ncm_sugerido),
      it.ncm_sugerido_curta ? h("div", { class: "cod-desc", title: it.ncm_sugerido_curta, text: it.ncm_sugerido_curta }) : null,
      it.confianca != null && it.regras.indexOf("NCM_MODELO") >= 0 ? h("div", { class: "conf", text: "modelo: " + Math.round(it.confianca * 100) + "%" }) : null);
  }
  function partes(txt) {
    var vistos = {};
    return (txt || "").split(" | ").map(function (x) { return x.trim(); }).filter(function (x) { if (!x || vistos[x]) return false; vistos[x] = 1; return true; });
  }
  function celulaMotivo(it, chave) {
    var nomes = S.dados.nomes_regras || {}, aberto = !!S.abertos[chave];
    var motivos = partes(it.motivo), acoes = it.semaforo !== "verde" ? partes(it.o_que_fazer) : [];
    var longo = motivos.length > 1 || acoes.length > 1 || (motivos[0] || "").length > 150;
    var div = h("div", { class: "c-motivo motivo" + (longo && !aberto ? " fechado" : "") });
    div.appendChild(h("span", { class: "rot-m", text: "Por quê" }));
    if (it.regras.length) div.appendChild(h("div", null, it.regras.map(function (r) { return h("span", { class: "regra", text: nomes[r] || r }); })));
    if (it.aceito) div.appendChild(h("span", { class: "pilula p-aceito", text: "aceito pela regra do escritório" }));
    if (!motivos.length) div.appendChild(h("span", { class: "vazio", text: "Nada encontrado." }));
    (aberto ? motivos : motivos.slice(0, 1)).forEach(function (m) { div.appendChild(h("span", { class: "texto", text: m })); });
    (aberto ? acoes : acoes.slice(0, 1)).forEach(function (a) { div.appendChild(h("span", { class: "fazer", text: a })); });
    if (longo) div.appendChild(h("button", { class: "mais", type: "button", onclick: function () { S.abertos[chave] = !aberto; renderTabela(); }, text: aberto ? "mostrar menos" : "ler tudo" + (motivos.length + acoes.length > 2 ? " (" + (motivos.length) + " alertas)" : "") }));
    return div;
  }

  function renderTabela() {
    var j = S.dados, cad = j.tipo === "cadastro", el = limpa($("tabela"));
    el.classList.toggle("cad", cad);
    var lista = itensFiltrados(), total = lista.length;
    var paginas = Math.max(1, Math.ceil(total / POR_PAGINA));
    if (S.pagina >= paginas) S.pagina = paginas - 1;
    var ini = S.pagina * POR_PAGINA, fatia = lista.slice(ini, ini + POR_PAGINA);
    var cab = cad
      ? ["Trocar", "Semáforo", "Produto", "NCM atual", "Sugerido", "Por quê e o que fazer"]
      : ["Semáforo", "Produto", "NCM da nota", "Sugerido", "CFOP", "Por quê e o que fazer"];
    el.appendChild(h("div", { class: "linha cab", role: "row" }, cab.map(function (c) { return h("div", { role: "columnheader", text: c }); })));
    if (!fatia.length) el.appendChild(h("div", { class: "tab-vazia", text: "Nenhum item com esse filtro." }));
    fatia.forEach(function (it) {
      var chave = cad ? "l" + it.linha : "i" + it.id;
      var pil = h("span", { class: "pilula p-" + it.semaforo }, h("span", { class: "ponto " + it.semaforo }), ROTULO[it.semaforo]);
      var linha = h("div", { class: "linha v-" + it.semaforo, role: "row" });
      if (cad) {
        var cb = h("input", { type: "checkbox", "aria-label": "Trocar o NCM de " + it.descricao + " pelo sugerido", disabled: !it.ncm_sugerido });
        cb.checked = !!S.marcados[it.linha];
        cb.addEventListener("change", function () { if (cb.checked) S.marcados[it.linha] = true; else delete S.marcados[it.linha]; renderBaixar(); });
        linha.appendChild(h("label", { class: "marcar" }, cb, h("span", { class: "rot-m", text: it.ncm_sugerido ? "Trocar pelo sugerido" : "Sem sugestão" })));
        linha.appendChild(h("div", { class: "c-sem" }, pil, h("span", { class: "conf", text: "linha " + it.linha_planilha })));
        linha.appendChild(h("div", { class: "c-prod" }, h("div", { class: "prod", text: it.descricao || "(sem descrição)" }), h("div", { class: "prod-meta", text: [it.codigo ? "Código " + it.codigo : "", it.gtin ? "GTIN " + it.gtin : ""].filter(Boolean).join(" · ") })));
        linha.appendChild(celulaNcm(it.ncm, it.ncm_curta, it.semaforo === "vermelho" && it.ncm_sugerido, "NCM atual"));
        linha.appendChild(celulaSug(it));
        linha.appendChild(celulaMotivo(it, chave));
      } else {
        linha.appendChild(h("div", { class: "c-sem" }, pil, h("span", { class: "conf", text: moeda(it.valor) })));
        var emp = (S.dados.empresas || []).filter(function (e) { return e.grupo === it.grupo; })[0];
        var meta = [emp && (S.dados.empresas || []).length > 1 ? emp.nome : "", it.modelo + " " + it.numero, "item " + it.n_item, it.data, it.sentido === "entrada" ? "compra" : ""].filter(Boolean).join(" · ");
        linha.appendChild(h("div", { class: "c-prod" }, h("div", { class: "prod", text: it.descricao || "(sem descrição)" }), h("div", { class: "prod-meta", text: meta })));
        linha.appendChild(celulaNcm(it.ncm, it.ncm_curta, it.semaforo === "vermelho" && it.ncm_sugerido, "NCM da nota"));
        linha.appendChild(celulaSug(it));
        linha.appendChild(h("div", { class: "c-cfop" }, h("span", { class: "rot-m", text: "CFOP" }), h("span", { class: "cod" + (it.cfop_sugerido ? " ruim" : ""), text: it.cfop || "-" }), it.cfop_sugerido ? h("span", { class: "cod cfop-sug", text: "→ " + it.cfop_sugerido }) : null));
        linha.appendChild(celulaMotivo(it, chave));
      }
      el.appendChild(linha);
    });
    var pg = limpa($("paginacao"));
    var info = total ? "Mostrando " + num(ini + 1) + " a " + num(Math.min(ini + POR_PAGINA, total)) + " de " + num(total) : "0 itens";
    if (S.dados.itens_omitidos && S.filtro !== "vermelho" && S.filtro !== "amarelo") info += " (mais " + num(S.dados.itens_omitidos) + " verdes só na planilha)";
    pg.appendChild(h("span", { text: info }));
    if (paginas > 1) pg.appendChild(h("span", { class: "pag-btns" },
      h("button", { class: "btn btn-sec", type: "button", disabled: S.pagina === 0, onclick: function () { S.pagina--; renderTabela(); $("tabela").scrollIntoView({ block: "start" }); } }, "Anterior"),
      h("button", { class: "btn btn-sec", type: "button", disabled: S.pagina >= paginas - 1, onclick: function () { S.pagina++; renderTabela(); $("tabela").scrollIntoView({ block: "start" }); } }, "Próxima")));
  }

  /* ---------------- baixar e corrigir ---------------- */
  function sistemaAtual() {
    var id = $("sel-sistema").value;
    return (S.estado.sistemas || []).filter(function (s) { return s.id === id; })[0];
  }
  function renderBaixar() {
    if (!S.estado) return;
    var j = S.dados, cad = j.tipo === "cadastro", sel = $("sel-sistema");
    if (!sel.options.length) S.estado.sistemas.forEach(function (s) { sel.appendChild(h("option", { value: s.id, text: s.nome })); });
    if (cad && j.bling && !sel.dataset.mexeu) sel.value = "bling";
    var emp = $("sel-empresa");
    $("campo-empresa").hidden = cad || (j.empresas || []).length < 2;
    if (!cad) {
      var atual = S.empresa || emp.value;
      limpa(emp);
      emp.appendChild(h("option", { value: "", text: "Todas" }));
      (j.empresas || []).forEach(function (e) { emp.appendChild(h("option", { value: e.grupo, text: e.nome })); });
      emp.value = atual || "";
    }
    var s = sistemaAtual(), res = limpa($("sistema-resumo"));
    var marcados = Object.keys(S.marcados).length;
    var pronto = s.arquivo_pronto && cad && j.tem_id;
    res.appendChild(h("span", { class: "tag " + (pronto ? "pronto" : "lista"), text: pronto ? "arquivo pronto para importar" : "lista de correção" }));
    res.appendChild(h("br"));
    if (s.arquivo_pronto && !cad) res.appendChild(document.createTextNode("O " + s.nome + " atualiza o NCM pelo ID do produto, que não vem na nota. Aqui sai a lista; o arquivo pronto sai pela aba Cadastro, com a planilha exportada do " + s.nome + "."));
    else if (s.arquivo_pronto && cad && !j.tem_id) res.appendChild(document.createTextNode("Esta planilha não tem a coluna ID, que o " + s.nome + " usa como chave. Sai a lista; para o arquivo pronto, exporte os produtos do próprio " + s.nome + "."));
    else res.appendChild(document.createTextNode(s.resumo));
    $("baixar-txt").textContent = cad
      ? "Marque na tabela as sugestões que você aceita (" + marcados + " marcada" + (marcados === 1 ? "" : "s") + "). Só elas vão para o arquivo."
      : "Os produtos com NCM sugerido, um por linha, para corrigir no cadastro de cada empresa.";
    $("btn-exportar").textContent = cad ? (pronto ? "Baixar arquivo do " + s.nome : "Baixar lista de correção") : "Baixar lista de correção";
    $("btn-exportar").disabled = cad && !marcados;
    var ol = limpa($("passos-lista")); s.passos.forEach(function (p) { ol.appendChild(h("li", { text: p })); });
    var cu = limpa($("passos-cuidados")); s.cuidados.forEach(function (c) { cu.appendChild(h("div", { class: "cuidado", text: c })); });
    var fo = limpa($("passos-fontes"));
    if (s.fontes.length) { fo.appendChild(h("div", { text: "Fonte (ajuda oficial, 08/11/2026):" })); s.fontes.forEach(function (f) { fo.appendChild(h("a", { href: f, rel: "noopener", target: "_blank", text: f.replace(/^https?:\/\//, "").slice(0, 70) + (f.length > 78 ? "…" : "") })); }); }
    $("passos").hidden = !s.passos.length;
  }
  $("sel-sistema").addEventListener("change", function (e) { e.target.dataset.mexeu = "1"; renderBaixar(); });
  $("sel-empresa").addEventListener("change", function () { });
  $("btn-relatorio").addEventListener("click", function () {
    var b = $("btn-relatorio"); ocupado(b, true);
    api("/api/relatorio/" + encodeURIComponent(S.dados.token)).then(function (r) { return baixar(r, "raio-x.xlsx"); })
      .catch(function (e) { alert(e.message); }).then(function () { ocupado(b, false); });
  });
  $("btn-exportar").addEventListener("click", function () {
    var j = S.dados, corpo = { token: j.token, sistema: $("sel-sistema").value };
    if (j.tipo === "cadastro") {
      corpo.aprovados = j.itens.filter(function (it) { return S.marcados[it.linha] && it.ncm_sugerido; }).map(function (it) { return { linha: it.linha, ncm: it.ncm_sugerido }; });
    } else corpo.empresa = $("sel-empresa").value;
    var b = $("btn-exportar"); ocupado(b, true);
    api("/api/exportar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) })
      .then(function (r) { return baixar(r, "correcao.xlsx"); })
      .then(function (aviso) { if (aviso) alert(aviso.replace(/&#(\d+);/g, function (_, n) { return String.fromCharCode(n); })); })
      .catch(function (e) { alert(e.message); }).then(function () { ocupado(b, false); });
  });

  /* ---------------- chat (projeto Pergunte ao Simples), se estiver ligado ---------------- */
  function contextoChat() {
    if (!window.ChatSimples || !S.dados) return;
    var j = S.dados, r = j.resumo;
    var itens = j.itens.filter(function (it) { return it.semaforo !== "verde"; }).slice(0, 40).map(function (it) {
      return { semaforo: it.semaforo, descricao: it.descricao, ncm: it.ncm, ncm_sugerido: it.ncm_sugerido || "", cfop: it.cfop || "", cfop_sugerido: it.cfop_sugerido || "", regras: it.regras, motivo: (it.motivo || "").slice(0, 300) };
    });
    try {
      window.ChatSimples.definirContexto({
        origem: j.tipo, resumo: { notas: r.notas || 0, itens: r.itens || r.produtos || 0, vermelho: r.vermelho, amarelo: r.amarelo, verde: r.verde },
        por_regra: (j.por_regra || []).map(function (p) { return { regra: p.regra, nome: p.nome, vermelho: p.vermelho, amarelo: p.amarelo }; }),
        itens: itens
      });
    } catch (e) { /* chat com defeito não atrapalha o Raio-X */ }
  }
  function ligarChat(chat) {
    if (!chat || !chat.ativo || !chat.js) return;
    var sc = document.createElement("script");
    sc.src = chat.js; sc.defer = true;
    sc.onload = function () { $("bloco-chat").hidden = false; contextoChat(); };
    sc.onerror = function () { $("bloco-chat").hidden = true; };
    document.body.appendChild(sc);
  }

  /* ---------------- início ---------------- */
  api("/api/estado").then(function (e) {
    S.estado = e;
    $("rodape-tabela").textContent = "Tabela NCM oficial do Siscomex, " + e.tabela_ncm;
    if (!e.modelo) status("Atenção: o modelo de IA não está carregado neste servidor; só as regras estão rodando.", "erro");
    ligarChat(e.chat);
    if (/[?&]exemplo\b/.test(location.search)) $("btn-exemplo").click();
  }).catch(function () { status("Não consegui falar com o servidor. Recarregue a página.", "erro"); });
})();
