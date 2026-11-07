using Microsoft.Kiota.Abstractions.Authentication;
using Microsoft.Kiota.Http.HttpClientLibrary;
using Wasf.Review.Client;
using Wasf.Review.Components;

var builder = WebApplication.CreateBuilder(args);
var apiUrl = builder.Configuration["services:python-api:https:0"] ?? "https://localhost:8000";

builder.Services.AddRazorComponents();
builder.Services.AddSingleton(new ApiLocation(apiUrl));
builder.Services.AddHttpClient("wasf");
builder.Services.AddScoped(services =>
{
    var http = services.GetRequiredService<IHttpClientFactory>().CreateClient("wasf");
    var adapter = new HttpClientRequestAdapter(new AnonymousAuthenticationProvider(), httpClient: http) { BaseUrl = apiUrl };
    return new WasfClient(adapter);
});

var app = builder.Build();
app.MapStaticAssets();
app.UseAntiforgery();
app.MapRazorComponents<App>();
app.Run();

public record ApiLocation(string Url);
