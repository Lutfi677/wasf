var builder = DistributedApplication.CreateBuilder(args);

var api = builder.AddUvicornApp("python-api", "..", "core.api:app")
    .WithPip(install: false)
    .WithHttpEndpoint(port: 8000, env: "UVICORN_PORT");

builder.AddProject<Projects.Wasf_Review>("review")
    .WithReference(api)
    .WaitFor(api);

builder.Build().Run();
