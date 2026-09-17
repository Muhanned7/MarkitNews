/**
 * Database access has been consolidated into the FastAPI backend application.
 * All PostgreSQL connection pooling is handled exclusively by the backend's ThreadedConnectionPool.
 * Next.js does not maintain an independent database connection pool.
 */

export const BACKEND_URL = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default {
    url: BACKEND_URL
};