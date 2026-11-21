// Exporta funcoes, strings, grafo de chamadas e pseudo-C do programa aberto para JSON (CEW).
// Uso headless (argumentos depois do nome do script, ver analyzeHeadlessREADME "getScriptArgs"):
//   analyzeHeadless <pasta_proj> <nome_proj> -import <programa> -scriptPath <CEW>/scripts/ghidra
//     -postScript ExportarCEW.java <saida.json> [max_funcoes_pseudo_c] [segundos_por_funcao] -deleteProject
// Saida segue schemas/analise_programa.schema.json.
// @category CEW
// @runtime Java

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.framework.Application;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Program;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class ExportarCEW extends GhidraScript {

    private static String js(String s) {
        if (s == null) {
            return "null";
        }
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        b.append(String.format("\\u%04x", (int) c));
                    } else {
                        b.append(c);
                    }
            }
        }
        return b.append('"').toString();
    }

    private static String hex(Address a) {
        return "0x" + a.toString().replaceAll("^.*:", "");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            printerr("uso: ExportarCEW.java <saida.json> [max_funcoes_pseudo_c] [segundos_por_funcao]");
            return;
        }
        File saida = new File(args[0]);
        int maxPseudo = args.length > 1 ? Integer.parseInt(args[1]) : 200;
        int segundos = args.length > 2 ? Integer.parseInt(args[2]) : 30;
        Program p = currentProgram;

        DecompInterface dec = new DecompInterface();
        dec.openProgram(p);

        List<String> funcoes = new ArrayList<>();
        List<String> chamadas = new ArrayList<>();
        int decompiladas = 0;
        FunctionIterator it = p.getFunctionManager().getFunctions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Function f = it.next();
            String pseudo = null;
            String erro = null;
            if (!f.isExternal() && !f.isThunk() && decompiladas < maxPseudo) {
                DecompileResults r = dec.decompileFunction(f, segundos, monitor);
                if (r != null && r.decompileCompleted() && r.getDecompiledFunction() != null) {
                    pseudo = r.getDecompiledFunction().getC();
                } else {
                    erro = r == null ? "sem resultado" : r.getErrorMessage();
                }
                decompiladas++;
            }
            StringBuilder o = new StringBuilder("{");
            o.append("\"nome\":").append(js(f.getName(true)));
            o.append(",\"endereco\":").append(js(hex(f.getEntryPoint())));
            o.append(",\"tamanho_bytes\":").append(f.getBody().getNumAddresses());
            o.append(",\"assinatura\":").append(js(f.getSignature().getPrototypeString()));
            o.append(",\"convencao\":").append(js(f.getCallingConventionName()));
            o.append(",\"externa\":").append(f.isExternal());
            o.append(",\"thunk\":").append(f.isThunk());
            o.append(",\"pseudo_c\":").append(js(pseudo));
            o.append(",\"erro_decompilacao\":").append(js(erro));
            o.append("}");
            funcoes.add(o.toString());
            Set<Function> chamados = f.getCalledFunctions(monitor);
            for (Function c : chamados) {
                chamadas.add("{\"de\":" + js(hex(f.getEntryPoint())) + ",\"para\":" + js(hex(c.getEntryPoint())) + "}");
            }
        }
        dec.dispose();

        List<String> strings = new ArrayList<>();
        DataIterator di = p.getListing().getDefinedData(true);
        while (di.hasNext() && !monitor.isCancelled() && strings.size() < 50000) {
            Data d = di.next();
            if (d.hasStringValue()) {
                Object v = d.getValue();
                List<String> refs = new ArrayList<>();
                ReferenceIterator ri = p.getReferenceManager().getReferencesTo(d.getAddress());
                while (ri.hasNext() && refs.size() < 8) {
                    Reference ref = ri.next();
                    Function quem = p.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                    if (quem != null) {
                        String e = js(hex(quem.getEntryPoint()));
                        if (!refs.contains(e)) {
                            refs.add(e);
                        }
                    }
                }
                strings.add("{\"endereco\":" + js(hex(d.getAddress())) + ",\"valor\":" + js(v == null ? "" : v.toString())
                    + ",\"tipo\":" + js(d.getDataType().getName()) + ",\"referenciado_por\":[" + String.join(",", refs) + "]}");
            }
        }

        try (Writer w = new OutputStreamWriter(new FileOutputStream(saida), StandardCharsets.UTF_8)) {
            w.write("{\"schema_version\":\"1.0\",\"gerado_por\":\"cew-ghidra\"");
            w.write(",\"programa\":{\"nome\":" + js(p.getName()) + ",\"sha256\":" + js(p.getExecutableSHA256())
                + ",\"linguagem\":" + js(p.getLanguageID().getIdAsString()) + ",\"compilador\":" + js(p.getCompilerSpec().getCompilerSpecID().getIdAsString())
                + ",\"formato\":" + js(p.getExecutableFormat()) + ",\"endereco_base\":" + js(hex(p.getImageBase())) + "}");
            w.write(",\"ferramenta\":{\"nome\":\"Ghidra\",\"versao\":" + js(Application.getApplicationVersion()) + ",\"script\":\"scripts/ghidra/ExportarCEW.java\"}");
            w.write(",\"limites\":{\"max_funcoes_pseudo_c\":" + maxPseudo + ",\"segundos_por_funcao\":" + segundos + "}");
            w.write(",\"funcoes\":[" + String.join(",", funcoes) + "]");
            w.write(",\"strings\":[" + String.join(",", strings) + "]");
            w.write(",\"chamadas\":[" + String.join(",", chamadas) + "]}");
        }
        println("CEW: " + funcoes.size() + " funcoes, " + strings.size() + " strings, " + chamadas.size() + " chamadas -> " + saida);
    }
}
