// SQL 轻量着色：按设计稿的四色方案（关键字/字符串/数字/标点）
const KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "LIMIT", "JOIN", "LEFT", "INNER",
  "ON", "AS", "AND", "OR", "DESC", "ASC", "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND",
  "DISTINCT", "DATE", "NOT", "IN", "WITH", "HAVING", "CASE", "WHEN", "THEN", "ELSE",
  "END", "NULL", "IS", "LIKE", "BETWEEN", "EXISTS", "UNION", "STRFTIME",
]);

export interface SqlToken { t: string; c: string }

export function tokenizeSql(sql: string): SqlToken[] {
  const out: SqlToken[] = [];
  const re = /('[^']*')|(\d+(?:\.\d+)?)|([A-Za-z_一-龥][\w一-龥]*)|(\s+)|(.)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sql))) {
    if (m[1]) out.push({ t: m[0], c: "var(--str)" });
    else if (m[2]) out.push({ t: m[0], c: "var(--num)" });
    else if (m[3]) out.push({ t: m[0], c: KEYWORDS.has(m[0].toUpperCase()) ? "var(--kw)" : "var(--ink)" });
    else if (m[4]) out.push({ t: m[0], c: "var(--ink)" });
    else out.push({ t: m[0], c: "var(--pun)" });
  }
  return out;
}
