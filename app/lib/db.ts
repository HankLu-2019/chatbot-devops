import { Pool } from "pg";

const connectionString =
  process.env.DATABASE_URL ||
  "postgresql://postgres:postgres@localhost:5432/ragdb";

// Singleton pool — reused across requests in the same Node.js process.
const pool = new Pool({ connectionString });

export default pool;
