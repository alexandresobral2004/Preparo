export const TIPOS_PANELA = ["1ª vez", "2ª vez", "3ª vez", "APURO"] as const;
export type TipoPanela = (typeof TIPOS_PANELA)[number];

export type TabKey = "cabecalho" | "panelas" | "andamento" | "registros" | "calc" | "conta" | "usuarios";

export type PanelaEstado =
  | "vazia"
  | "sem_entrada"
  | "no_fogo"
  | "fervendo"
  | "colhida";

export interface ChacronaItemDraft {
  nucleo: string;
  kg: string;
}

export interface PanelaDraft {
  numero: number;
  tipo: TipoPanela | "";
  entrada: string;
  fervura: string;
  colhida: string;
  litros: string;
  litrosLocked: boolean;
  metaLitros?: string;
}

export interface BlocoAutoria {
  criadoPorId: number;
  criadoPorNome: string;
  criadoEm: string;
  editadoPorId?: number;
  editadoPorNome?: string;
  editadoEm?: string;
}

export interface BlocoDraft {
  obs: string;
  anotador: string;
  data: string;
  /** Calculada e devolvida pelo servidor; o cliente só exibe. */
  autoria?: BlocoAutoria | null;
  panelas: PanelaDraft[];
}

export interface PreparoDraft {
  id?: string;
  salvoEm?: string;
  /** Versão do rascunho no servidor; volta em cada gravação para detectar conflito. */
  _versao?: number;
  nucleo: string;
  data: string;
  mestre: string;
  auxiliar: string;
  respMariri: string;
  respChacrona: string;
  respChacrona2: string;
  mariri: string;
  maririKg: string;
  pesoSecaKg: string;
  pesoCheiaKg: string;
  /** c) Panela + mariri + chacrona + água (kg); um valor para todo o preparo. A água é c − b (1 kg ≈ 1 L). */
  pesoComAguaKg: string;
  chacrona: ChacronaItemDraft[];
  obsGeral: string;
  blocos: BlocoDraft[];
}

export interface RegistroSaved {
  id: string;
  salvoEm: string;
  nucleo: string;
  data: string;
  mestre: string;
  auxiliar: string;
  respMariri: string;
  respChacrona: string;
  respChacrona2: string;
  mariri: string;
  maririKg: number | null;
  chacrona: { nucleo: string; kg: number | null }[];
  obsGeral: string;
  origem?: string;
  criadoPor?: { id: number; nome: string } | null;
  atualizadoPor?: { id: number; nome: string } | null;
  blocos: {
    obs: string;
    anotador: string;
    data: string;
    autoria?: BlocoAutoria | null;
    panelas: {
      numero: number;
      tipo: TipoPanela | "";
      entrada: string;
      fervura: string;
      colhida: string;
      litros: number | null;
      pesoSecaKg: number | null;
      pesoCheiaKg: number | null;
      pesoComAguaKg?: number | null;
      metaLitros: number | null;
    }[];
  }[];
  chacronaTotalKg: number;
  totalLitros: number;
  totaisPorTipo: Record<TipoPanela, number>;
}

export interface LembreteItem {
  id: string;
  texto: string;
  horario: string;
  feito: boolean;
  criadoEm: string;
}

export interface ConfigAvisos {
  minSemFervura: number;
  horasSemColheita: number;
  metaLitrosPadrao: number;
}

export interface PanelaAlertas {
  faltando: string[];
  conferir: string[];
}

export interface CurvaPonto {
  min: number;
  litros: number;
}

export interface PanelaPrediction {
  disponivel: boolean;
  usaPesos?: boolean;
  aguardandoFervura?: boolean;
  passouDoPonto?: boolean;
  motivo?: string;
  metaLitros: number;
  pesoLiquidoInicialKg?: number | null;
  litrosIniciaisEstimados?: number | null;
  litrosAtuaisEstimados?: number | null;
  taxaEvaporacaoLh?: number | null;
  tempoFervuraAtualMin?: number | null;
  tempoFervuraAlvoMin?: number | null;
  minutosRestantes?: number | null;
  horarioRetiradaPrevisto?: string | null;
  margemErroLitros?: number;
  margemErroMinutos?: number;
  progressoPercentual?: number;
  modeloNivel?: "inicial" | "aprendendo" | "calibrado";
  amostrasUsadas?: number;
  maeLitros?: number | null;
  maeMinutos?: number | null;
  r2?: number | null;
  curva?: CurvaPonto[];
  aviso?: string | null;
}

export interface BlocoMetricas {
  totalLitros: number;
  tempoMedioMin: number | null;
  duracaoMin: number | null;
  litrosPorHora: number | null;
  minPorLitro: number | null;
}

export interface StatsTipoResumo {
  totalColhidas: number;
  comPesos: number;
  taxaEvaporacaoLh: number;
  fatorLiquidoInicial: number;
  modeloNivel: "inicial" | "aprendendo" | "calibrado";
  maeLitros: number | null;
  maeMinutos: number | null;
  r2: number | null;
}

export interface StatsSummary {
  totalPanelasColhidas: number;
  totalComPesos: number;
  modeloGeralNivel: "inicial" | "aprendendo" | "calibrado";
  maeLitrosGeral: number | null;
  maeMinutosGeral: number | null;
  r2Geral: number | null;
  porTipo: Record<TipoPanela, StatsTipoResumo>;
}

export interface PredictResponse {
  resumo: {
    noFogo: number;
    colhidas: number;
    comPendencias: number;
  };
  totais: {
    totalGeral: number;
    porTipo: Record<TipoPanela, number>;
  };
  modelo: StatsSummary;
  blocos: {
    blocoIndex: number;
    metricas: BlocoMetricas;
    panelas: {
      numero: number;
      estado: PanelaEstado;
      alertas: PanelaAlertas;
      predicao: PanelaPrediction;
    }[];
  }[];
}

export interface PesoSugestao {
  pesoKg: number;
  usos: number;
}

export interface Usuario {
  id: number;
  login: string;
  /** null em contas antigas, criadas antes do e-mail. */
  email: string | null;
  nome: string;
  papel: "admin" | "usuario";
  situacao: "pendente" | "ativo" | "inativo";
  /** Valor de GRAUS ("" para usuário antigo sem grau informado). */
  grau: string;
  nucleo: string;
}

/** 'editar' escreve no preparo; 'acompanhar' só lê. Quem autoriza é o dono do preparo. */
export type PermissaoMembro = "editar" | "acompanhar";

export interface PreparoResumo {
  id: string;
  nome: string;
  donoNome: string;
  meuPapel: "dono" | "membro" | null;
  minhaSituacao: "aprovado" | "pendente" | "recusado" | null;
  /** 'editar' para o dono e para quem recebeu essa permissão; null se não está aprovado. */
  minhaPermissao: PermissaoMembro | null;
  pendentes: number;
}

export interface MembroPreparo {
  usuarioId: number;
  nome: string;
  login: string;
  email: string | null;
  papel: "dono" | "membro";
  situacao: "aprovado" | "pendente" | "recusado";
  permissao: "editar" | "acompanhar";
}
