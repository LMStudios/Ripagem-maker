type Config = { url: string; publicKey: string; secretKey: string };
type Payload = Record<string, unknown>;
type Perfil = {
  id: string;
  nome: string;
  codigo: string;
  funcao: "editor" | "administrador";
  ativo: boolean;
};
type Usuario = { id: string; email?: string; last_sign_in_at?: string };
type RequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  json?: Payload;
  bearer?: string;
  prefer?: string;
};

const fields = "id,nome,codigo,funcao,ativo";
const pageSize = 100;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const jwt = /^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$/;
const headers = { "Cache-Control": "no-store" };

class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

function required(value: unknown, field: string, expression: RegExp) {
  if (typeof value !== "string" || !expression.test(value)) {
    throw new ApiError(400, `Confira o campo ${field}.`);
  }
  return value;
}

function profileInput(body: Payload) {
  const nome = required(
    typeof body.nome === "string" ? body.nome.trim() : body.nome,
    "nome",
    /^[^\p{Cc}]{1,100}$/u,
  );
  const codigo = required(
    typeof body.codigo === "string"
      ? body.codigo.trim().toUpperCase()
      : body.codigo,
    "código",
    /^[A-Z0-9][A-Z0-9_-]{0,23}$/,
  );
  return { nome, codigo };
}

function merge(perfil: Perfil, usuario?: Usuario) {
  return {
    id: perfil.id,
    nome: perfil.nome,
    codigo: perfil.codigo,
    funcao: perfil.funcao,
    ativo: perfil.ativo,
    email: usuario?.email ?? null,
    ultimo_login: usuario?.last_sign_in_at ?? null,
  };
}

function profiles(filters: Record<string, string> = {}) {
  return "/rest/v1/perfis?" +
    new URLSearchParams({ select: fields, ...filters });
}

export function createHandler(conf: Config, request = fetch) {
  async function call<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const { method = "GET", json, bearer, prefer } = options;
    const key = bearer ? conf.publicKey : conf.secretKey;
    const requestHeaders = new Headers({
      apikey: key,
      Accept: "application/json",
    });
    if (bearer || !key.startsWith("sb_secret_")) {
      requestHeaders.set("Authorization", `Bearer ${bearer ?? key}`);
    }
    if (json) requestHeaders.set("Content-Type", "application/json");
    if (prefer) requestHeaders.set("Prefer", prefer);
    const result = await request(new URL(conf.url + path), {
      method,
      headers: requestHeaders,
      body: json ? JSON.stringify(json) : undefined,
      redirect: "error",
      signal: AbortSignal.timeout(8_000),
    });
    if (result.ok) return await result.json() as T;
    const error: Payload = await result.json().catch(() => ({}));
    if (
      path === "/auth/v1/user" &&
      (result.status === 401 || result.status === 403)
    ) {
      throw new ApiError(401, "Sessão inválida. Entre novamente.");
    }
    if (
      error.code === "23505" || error.error_code === "user_already_exists" ||
      error.error_code === "email_exists"
    ) {
      throw new ApiError(
        409,
        "Já existe um perfil com este e-mail ou código de editor.",
      );
    }
    if (result.status === 429) {
      throw new ApiError(
        429,
        "O serviço limitou as solicitações. Tente novamente mais tarde.",
      );
    }
    if (path === "/auth/v1/invite" && result.status === 400) {
      throw new ApiError(
        400,
        "O convite não foi enviado. Confira o e-mail e a configuração de envio.",
      );
    }
    throw new ApiError(502, "O serviço da equipe está indisponível.");
  }

  async function list() {
    const rows: Perfil[] = [];
    for (let offset = 0;; offset += pageSize) {
      const page = await call<Perfil[]>(profiles({
        order: "nome.asc,id.asc",
        limit: String(pageSize),
        offset: String(offset),
      }));
      rows.push(...page);
      if (page.length < pageSize) break;
    }
    const remaining = new Set(rows.map((row) => row.id));
    const accounts = new Map<string, Usuario>();
    for (let page = 1; remaining.size; page++) {
      const { users } = await call<{ users: Usuario[] }>(
        `/auth/v1/admin/users?page=${page}&per_page=${pageSize}`,
      );
      for (const user of users) {
        if (remaining.delete(user.id)) accounts.set(user.id, user);
      }
      if (users.length < pageSize) break;
    }
    return { perfis: rows.map((row) => merge(row, accounts.get(row.id))) };
  }

  async function invite(body: Payload) {
    const { nome, codigo } = profileInput(body);
    const email = required(
      typeof body.email === "string"
        ? body.email.trim().toLowerCase()
        : body.email,
      "e-mail",
      /^(?=.{3,254}$)[^\s@]+@[^\s@]+\.[^\s@]+$/,
    );
    const existing = await call<Perfil[]>(
      profiles({ codigo: `eq.${codigo}`, limit: "1" }),
    );
    if (existing.length) {
      throw new ApiError(409, "Este código de editor já está em uso.");
    }
    const convite = await call<Usuario | { user: Usuario }>("/auth/v1/invite", {
      method: "POST",
      json: { email },
    });
    const invited = "user" in convite ? convite.user : convite;
    if (typeof invited?.id !== "string" || !uuid.test(invited.id)) {
      throw new ApiError(
        502,
        "O serviço não confirmou o convite. Confira Usuários no painel do Supabase.",
      );
    }
    const [perfil] = await call<Perfil[]>(profiles(), {
      method: "POST",
      json: { id: invited.id, nome, codigo, funcao: "editor", ativo: true },
      prefer: "return=representation",
    });
    return { perfil: merge(perfil, invited) };
  }

  async function update(body: Payload) {
    const id = required(body.id, "identificador", uuid);
    const change = body.acao === "editar"
      ? profileInput(body)
      : { ativo: body.acao === "reativar" };
    const filter: Record<string, string> = { id: `eq.${id}` };
    if (body.acao === "desativar") filter.funcao = "eq.editor";
    const [perfil] = await call<Perfil[]>(profiles(filter), {
      method: "PATCH",
      json: change,
      prefer: "return=representation",
    });
    if (!perfil) {
      const message = body.acao === "desativar"
        ? "Selecione um editor existente para desativar."
        : "Perfil não encontrado.";
      throw new ApiError(404, message);
    }
    // O perfil é a autorização da equipe. A identidade de Auth
    // continua vinculada à conta para permitir reativação.
    return { perfil };
  }

  return async (req: Request) => {
    if (req.method !== "POST") {
      return Response.json({ erro: "Use POST." }, {
        status: 405,
        headers: { ...headers, Allow: "POST" },
      });
    }
    try {
      const bearer = jwt.exec(req.headers.get("Authorization") ?? "")?.[1];
      if (!bearer) throw new ApiError(401, "Entre para consultar a equipe.");
      const user = await call<Usuario>("/auth/v1/user", { bearer });
      if (typeof user?.id !== "string" || !uuid.test(user.id)) {
        throw new ApiError(401, "Sessão inválida. Entre novamente.");
      }
      const [caller] = await call<Perfil[]>(
        profiles({ id: `eq.${user.id}`, limit: "1" }),
        { bearer },
      );
      if (
        !caller || caller.id !== user.id || caller.funcao !== "administrador" ||
        !caller.ativo
      ) {
        throw new ApiError(
          403,
          "Somente um administrador ativo pode consultar a equipe.",
        );
      }
      const raw = await req.text();
      if (raw.length > 4096) {
        throw new ApiError(413, "A solicitação ficou maior que o permitido.");
      }
      let body: Payload;
      try {
        body = JSON.parse(raw);
        if (!body || typeof body !== "object" || Array.isArray(body)) {
          throw new TypeError();
        }
      } catch {
        throw new ApiError(400, "Confira os dados enviados.");
      }
      switch (body.acao) {
        case "listar":
          return Response.json(await list(), { headers });
        case "convidar":
          return Response.json(await invite(body), { status: 201, headers });
        case "editar":
        case "desativar":
        case "reativar":
          return Response.json(await update(body), { headers });
        default:
          throw new ApiError(400, "Ação da equipe desconhecida.");
      }
    } catch (error) {
      if (error instanceof ApiError) {
        return Response.json({ erro: error.message }, {
          status: error.status,
          headers,
        });
      }
      return Response.json({
        erro: "Não foi possível acessar o serviço da equipe.",
      }, { status: 502, headers });
    }
  };
}

function configuredKey(keyring: string, fallback: string) {
  const keys = JSON.parse(Deno.env.get(keyring) || "{}");
  return keys.default ?? Deno.env.get(fallback);
}

if (import.meta.main) {
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/+$/, "");
  const publicKey = configuredKey(
    "SUPABASE_PUBLISHABLE_KEYS",
    "SUPABASE_ANON_KEY",
  );
  const secretKey = configuredKey(
    "SUPABASE_SECRET_KEYS",
    "SUPABASE_SERVICE_ROLE_KEY",
  );
  if (!url || !publicKey || !secretKey) {
    throw new Error("Configure as variáveis do Supabase para a função.");
  }
  Deno.serve(createHandler({ url, publicKey, secretKey }));
}
