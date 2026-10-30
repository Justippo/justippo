import React from "react";

interface ErrorProps {
  statusCode: number | null;
}

function Error({ statusCode }: ErrorProps) {
  return (
    <main
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        fontFamily: "system-ui, -apple-system, sans-serif",
        padding: "2rem",
      }}
    >
      <div style={{ textAlign: "center" }}>
        <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
          {statusCode ? `${statusCode} Error` : "An error occurred"}
        </h1>
        <p style={{ color: "#666", marginBottom: "1.5rem" }}>
          {statusCode === 404
            ? "The page you requested does not exist."
            : "Something went wrong. Please try again."}
        </p>
        <a
          href="/"
          style={{
            color: "#005796",
            textDecoration: "underline",
            fontSize: "1rem",
          }}
        >
          Go to home
        </a>
      </div>
    </main>
  );
}

Error.getInitialProps = ({
  res,
  err,
}: {
  res?: { statusCode?: number };
  err?: { statusCode?: number };
}) => {
  const statusCode = res?.statusCode ?? err?.statusCode ?? 404;
  return { statusCode };
};

export default Error;
