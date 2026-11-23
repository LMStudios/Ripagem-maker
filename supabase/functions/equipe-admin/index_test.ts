import { createHandler } from "./index.ts";

const admin = "82150ba1-9ba5-4995-9d2d-493670b0574b";
const editor = "78075be1-d236-4593-a81c-06ec62b3f6b4";
const bearer = "test.valid.jwt";
const perfis = [{
  id: admin,
  nome: "Admin",
  codigo: "EV00",
  funcao: "administrador",
  ativo: true,
}, {
  id: editor,
  nome: "Editor",
  codigo: "EV08",
  funcao: "editor",
  ativo: true,
}];

function assert<T>(actual: T, expected: T) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `Esperado ${JSON.stringify(expected)}, recebido ${
        JSON.stringify(actual)
      }`,
    );
  }
}

function app({
  caller = perfis[0],
  valid = true,
  preexisting = false,
  newKey = true,
}: {
  caller?: typeof perfis[number];
  valid?: boolean;
  preexisting?: boolean;
  newKey?: boolean;
} = {}) {
  const calls: {
    url: URL;
    method: string | undefined;
    body: unknown;
    headers: Headers;
  }[] = [];
  const conf = {
    url: "https://teste.supabase.co",
    publicKey: "sb_publishable_teste",
    secretKey: newKey ? "sb_secret_teste" : "legacy.server.key",
  };
  const handler = createHandler(conf, (input, init) => {
    const url = new URL(String(input));
    const headers = new Headers(init?.headers);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    const method = init?.method;
    calls.push({ url, method, body, headers });
    const respond = (data: unknown, status = 200) =>
      Promise.resolve(Response.json(data, { status }));
    if (url.pathname === "/auth/v1/user") {
      assert(headers.get("apikey"), conf.publicKey);
      assert(headers.get("Authorization"), `Bearer ${bearer}`);
      return valid
        ? respond({ id: caller.id, user_metadata: { role: "administrador" } })
        : respond({}, 403);
    }
    if (headers.get("apikey") === conf.publicKey) {
      assert(url.searchParams.get("id"), `eq.${caller.id}`);
      assert(headers.get("Authorization"), `Bearer ${bearer}`);
      return respond([caller]);
    }
    assert(headers.get("apikey"), conf.secretKey);
    assert(
      headers.get("Authorization"),
      newKey ? null : `Bearer ${conf.secretKey}`,
    );
    if (url.pathname === "/auth/v1/admin/users") {
      return respond({
        users: [
          { id: admin, email: "admin@exemplo.com", last_sign_in_at: null },
          {
            id: editor,
            email: "editor@exemplo.com",
            last_sign_in_at: "2026-11-20T12:00:00Z",
            secret_metadata: "deve ficar no servidor",
          },
        ],
      });
    }
    if (url.pathname === "/auth/v1/admin/generate_link") {
      return respond({ id: editor, email_otp: "928164", action_link: "https://should-not-be-returned.test" });
    }
    if (url.pathname === "/auth/v1/invite") {
      return respond({ id: editor, email: "editor@exemplo.com" });
    }
    if (method === "GET") {
      if (url.searchParams.has("codigo")) {
        return respond(preexisting ? [perfis[1]] : []);
      }
      return respond(perfis);
    }
    if (
      method === "PATCH" && url.searchParams.get("funcao") === "eq.editor" &&
      url.searchParams.get("id") === `eq.${admin}`
    ) {
      return respond([]);
    }
    return respond([{ ...perfis[1], ...body }], 201);
  });
  const action = (
    body: object,
    authorization: string | null = `Bearer ${bearer}`,
  ) =>
    handler(
      new Request("https://teste.supabase.co/functions/v1/equipe-admin", {
        method: "POST",
        headers: authorization ? { Authorization: authorization } : undefined,
        body: JSON.stringify(body),
      }),
    );
  return { action, calls };
}

Deno.test("exige JWT e valida a identidade antes de consultar perfis", async () => {
  const client = app({ valid: false });
  assert((await client.action({ acao: "listar" }, null)).status, 401);
  assert(
    (await client.action({ acao: "listar" }, "Bearer sb_publishable_teste"))
      .status,
    401,
  );
  assert(client.calls.length, 0);
  assert((await client.action({ acao: "listar" })).status, 401);
  assert(client.calls.length, 1);
});

Deno.test("editor e administrador desativado recebem 403 antes de qualquer chamada privilegiada", async () => {
  for (const caller of [perfis[1], { ...perfis[0], ativo: false }]) {
    const client = app({ caller });
    assert(
      (await client.action({ acao: "listar", funcao: "administrador" })).status,
      403,
    );
    assert(client.calls.length, 2);
  }
});

Deno.test("admin consulta apenas campos de perfil e último login, com a chave legada opcional", async () => {
  for (const newKey of [true, false]) {
    const client = app({ newKey });
    const response = await client.action({ acao: "listar" });
    assert(response.status, 200);
    const result = await response.json();
    assert(result.perfis[1], {
      ...perfis[1],
      email: "editor@exemplo.com",
      ultimo_login: "2026-11-20T12:00:00Z",
    });
  }
});

Deno.test("convite usa nome e código limpos e cria apenas editor", async () => {
  const client = app();
  const response = await client.action({
    acao: "convidar",
    email: " EDITOR@EXEMPLO.COM ",
    nome: " Editor ",
    codigo: "ev08",
    funcao: "administrador",
    ativo: false,
  });
  const last = client.calls.at(-1);
  assert(response.status, 201);
  assert(last?.body, perfis[1]);
  assert(
    client.calls.find((item) => item.url.pathname === "/auth/v1/invite")?.body,
    {
      email: "editor@exemplo.com",
    },
  );
});

Deno.test("código já cadastrado retorna conflito antes de disparar convite", async () => {
  const client = app({ preexisting: true });
  const response = await client.action({
    acao: "convidar",
    email: "editor@exemplo.com",
    nome: "Editor",
    codigo: "EV08",
  });
  assert(response.status, 409);
  assert(
    client.calls.some((item) => item.url.pathname === "/auth/v1/invite"),
    false,
  );
});

Deno.test("edição só altera nome e código e desativação só alcança editor", async () => {
  const client = app();
  const changed = await client.action({
    acao: "editar",
    id: editor,
    nome: "Editor",
    codigo: "EV09",
    ativo: false,
    funcao: "administrador",
  });
  assert(changed.status, 200);
  assert(client.calls.at(-1)?.body, { nome: "Editor", codigo: "EV09" });
  const disabled = await client.action({ acao: "desativar", id: editor });
  assert(disabled.status, 200);
  assert(client.calls.at(-1)?.url.searchParams.get("funcao"), "eq.editor");
  assert(client.calls.at(-1)?.body, { ativo: false });
  const blocked = await client.action({ acao: "desativar", id: admin });
  assert(blocked.status, 404);
});

Deno.test("gera código manual para ativar no app sem enviar e-mail", async () => {
  const client = app();
  const response = await client.action({
    acao: "convidar", email: "editor@exemplo.com", nome: "Editor",
    codigo: "EV08", convite_manual: true,
  });
  assert(response.status, 201);
  const result = await response.json();
  assert(result.codigo_ativacao, "928164");
  assert(result.action_link, undefined);
  assert(client.calls.find((item) => item.url.pathname === "/auth/v1/admin/generate_link")?.body,
    { type: "invite", email: "editor@exemplo.com" });
  assert(client.calls.some((item) => item.url.pathname === "/auth/v1/invite"), false);
});
