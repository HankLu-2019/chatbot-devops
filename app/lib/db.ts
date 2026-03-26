import { Pool } from "pg";

const connectionString =
  process.env.DATABASE_URL ||
  "postgresql://postgres:postgres@localhost:5432/ragdb";

// Singleton pool — reused across requests in the same Node.js process.
const pool = new Pool({
  connectionString,
  max: 10,              // max connections in pool (default 10, explicit for clarity)
  idleTimeoutMillis: 30_000,   // close idle connections after 30s
  connectionTimeoutMillis: 3_000, // fail fast if DB is unreachable
});

export default pool;
