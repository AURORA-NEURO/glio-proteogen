import {
  arrayAt,
  isJsonObject,
  numberAt,
  textAt,
  type JsonObject,
  type NormalizedState,
  type StateKind,
} from "./research-state";

export const GRAPH_KIND_ORDER: StateKind[] = [
  "protein",
  "proteoform",
  "phosphosite",
  "complex",
  "pathway",
  "kinase",
  "other",
];

export const GRAPH_NODE_WIDTH = 184;
export const GRAPH_NODE_HEIGHT = 68;

const COLUMN_GAP = 108;
const ROW_GAP = 28;
const CANVAS_MARGIN_X = 30;
const CANVAS_HEADER_HEIGHT = 58;
const CANVAS_FOOTER_HEIGHT = 34;

export type EvidenceGraphColumn = {
  kind: StateKind;
  index: number;
  x: number;
  nodeCount: number;
};

export type EvidenceGraphNode = {
  id: string;
  label: string;
  kind: StateKind;
  column: number;
  row: number;
  x: number;
  y: number;
  state: NormalizedState | null;
};

export type EvidenceGraphEdge = {
  id: string;
  sourceId: string;
  targetId: string;
  kind: string;
  sign: -1 | 1;
  weight: number;
  essential: boolean;
  path: string;
  labelX: number;
  labelY: number;
};

export type EvidenceGraphLayout = {
  columns: EvidenceGraphColumn[];
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  width: number;
  height: number;
};

function compareText(left: string, right: string): number {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

function requestKind(value: string): StateKind {
  return GRAPH_KIND_ORDER.includes(value as StateKind) ? value as StateKind : "other";
}

function edgeGeometry(
  source: EvidenceGraphNode,
  target: EvidenceGraphNode,
  sameColumnOffset: number,
): { path: string; labelX: number; labelY: number } {
  const sourceCenterY = source.y + GRAPH_NODE_HEIGHT / 2;
  const targetCenterY = target.y + GRAPH_NODE_HEIGHT / 2;
  if (source.column === target.column) {
    const routeX = source.x + GRAPH_NODE_WIDTH + 35 + sameColumnOffset;
    return {
      path: `M ${source.x + GRAPH_NODE_WIDTH} ${sourceCenterY} C ${routeX} ${sourceCenterY}, ${routeX} ${targetCenterY}, ${target.x + GRAPH_NODE_WIDTH} ${targetCenterY}`,
      labelX: routeX,
      labelY: (sourceCenterY + targetCenterY) / 2,
    };
  }

  const movesRight = source.x < target.x;
  const sourceX = movesRight ? source.x + GRAPH_NODE_WIDTH : source.x;
  const targetX = movesRight ? target.x : target.x + GRAPH_NODE_WIDTH;
  const distance = targetX - sourceX;
  return {
    path: `M ${sourceX} ${sourceCenterY} C ${sourceX + distance * 0.42} ${sourceCenterY}, ${targetX - distance * 0.42} ${targetCenterY}, ${targetX} ${targetCenterY}`,
    labelX: (sourceX + targetX) / 2,
    labelY: (sourceCenterY + targetCenterY) / 2,
  };
}

export function describeGraphEdge(edge: Pick<EvidenceGraphEdge, "id" | "sourceId" | "targetId" | "kind" | "sign" | "weight" | "essential">): string {
  const sign = edge.sign > 0 ? "positive" : "negative";
  const essential = edge.essential ? ", essential" : "";
  return `${edge.id}: ${edge.sourceId} to ${edge.targetId}; ${edge.kind}; ${sign} sign; weight ${edge.weight}${essential}`;
}

export function buildEvidenceGraph(request: JsonObject, states: NormalizedState[]): EvidenceGraphLayout {
  const statesById = new Map(states.map((state) => [state.id, state]));
  const requestNodes = arrayAt(request, ["nodes"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const id = textAt(value, ["node_id"]);
    if (!id) return [];
    return [{
      id,
      label: textAt(value, ["display_name"], id),
      kind: requestKind(textAt(value, ["kind"], "other")),
    }];
  });

  const presentKinds = GRAPH_KIND_ORDER.filter((kind) => requestNodes.some((node) => node.kind === kind));
  const columns = presentKinds.map((kind, index) => ({
    kind,
    index,
    x: CANVAS_MARGIN_X + index * (GRAPH_NODE_WIDTH + COLUMN_GAP),
    nodeCount: requestNodes.filter((node) => node.kind === kind).length,
  }));
  const columnByKind = new Map(columns.map((column) => [column.kind, column]));
  const rowByKind = new Map<StateKind, number>();
  const nodes = [...requestNodes]
    .sort((left, right) => {
      const kindOrder = GRAPH_KIND_ORDER.indexOf(left.kind) - GRAPH_KIND_ORDER.indexOf(right.kind);
      return kindOrder || compareText(left.id, right.id);
    })
    .map<EvidenceGraphNode>((node) => {
      const column = columnByKind.get(node.kind);
      const row = rowByKind.get(node.kind) ?? 0;
      rowByKind.set(node.kind, row + 1);
      return {
        ...node,
        column: column?.index ?? 0,
        row,
        x: column?.x ?? CANVAS_MARGIN_X,
        y: CANVAS_HEADER_HEIGHT + row * (GRAPH_NODE_HEIGHT + ROW_GAP),
        state: statesById.get(node.id) ?? null,
      };
    });

  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const sameColumnCounts = new Map<number, number>();
  const edges = arrayAt(request, ["edges"]).flatMap((value) => {
    if (!isJsonObject(value)) return [];
    const id = textAt(value, ["edge_id"]);
    const sourceId = textAt(value, ["source_id"]);
    const targetId = textAt(value, ["target_id"]);
    const source = nodeById.get(sourceId);
    const target = nodeById.get(targetId);
    const sign = numberAt(value, ["sign"]);
    const weight = numberAt(value, ["weight"]);
    if (!id || !source || !target || (sign !== -1 && sign !== 1) || weight === null) return [];
    return [{
      id,
      sourceId,
      targetId,
      kind: textAt(value, ["kind"], "relation"),
      sign: sign as -1 | 1,
      weight,
      essential: value.essential === true,
      source,
      target,
    }];
  }).sort((left, right) => compareText(left.id, right.id)).map<EvidenceGraphEdge>((edge) => {
    const sameColumn = edge.source.column === edge.target.column;
    const count = sameColumnCounts.get(edge.source.column) ?? 0;
    if (sameColumn) sameColumnCounts.set(edge.source.column, count + 1);
    const geometry = edgeGeometry(edge.source, edge.target, sameColumn ? (count % 4) * 12 : 0);
    return {
      id: edge.id,
      sourceId: edge.sourceId,
      targetId: edge.targetId,
      kind: edge.kind,
      sign: edge.sign,
      weight: edge.weight,
      essential: edge.essential,
      ...geometry,
    };
  });

  const maximumRows = Math.max(1, ...columns.map((column) => column.nodeCount));
  const width = Math.max(
    360,
    CANVAS_MARGIN_X * 2 + columns.length * GRAPH_NODE_WIDTH + Math.max(0, columns.length - 1) * COLUMN_GAP,
  );
  const height = CANVAS_HEADER_HEIGHT + maximumRows * GRAPH_NODE_HEIGHT + Math.max(0, maximumRows - 1) * ROW_GAP + CANVAS_FOOTER_HEIGHT;
  return { columns, nodes, edges, width, height };
}
