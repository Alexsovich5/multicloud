"""
Static GraphiQL page served on ``GET /graphql`` for browsers.

Nothing from the request is rendered into the page and no query runs while
serving it. The page asks for the API key once, keeps it in sessionStorage
for the tab, and sends it as ``Authorization: Bearer <key>`` on every
GraphQL request. A 401 answer clears the stored key. The editor never
pre-fills a query from the URL, so a link cannot stage a mutation for the
operator to run. The GraphiQL and React
files come from jsdelivr with Subresource Integrity hashes.
"""

PAGE = '''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>multicloud GraphiQL</title>
  <meta name="referrer" content="no-referrer">
  <style>
    html, body { height: 100%; margin: 0; overflow: hidden; width: 100%; }
  </style>
  <link href="https://cdn.jsdelivr.net/npm/graphiql@0.11.11/graphiql.css" rel="stylesheet"
        integrity="sha384-vkAfvD3+VOwIO7O2Fbo3U2Bj6dX6IdQm6PpKTw9hP7Cn18fTDhEtZEF6GhfRCMFs"
        crossorigin="anonymous">
  <script src="https://cdn.jsdelivr.net/npm/react@15.6.2/dist/react.min.js"
          integrity="sha384-ddefOBuuNyTM/Cmow+OyNByTvyFn+WsOZoEeef8i9foAbxVX7H05qiV6kCQBLMaq"
          crossorigin="anonymous"></script>
  <script src="https://cdn.jsdelivr.net/npm/react-dom@15.6.2/dist/react-dom.min.js"
          integrity="sha384-8azwCFabBTGjDNlgOl3wEErYldnYEYPf7WicitIXomz+TE7mfO+r9NC+uT7zZRs4"
          crossorigin="anonymous"></script>
  <script src="https://cdn.jsdelivr.net/npm/graphiql@0.11.11/graphiql.min.js"
          integrity="sha384-gW+d8pv4EUvvHXbqLad+C/u/f+yDBzoqAvdPpIWVEtdTiYf9qiADDOqN6+G6hg6Y"
          crossorigin="anonymous"></script>
</head>
<body>
  <script>
    var KEY_NAME = 'multicloud-api-key';

    function apiKey() {
      var key = window.sessionStorage.getItem(KEY_NAME);
      if (!key) {
        key = window.prompt('API key for this multicloud API') || '';
        window.sessionStorage.setItem(KEY_NAME, key);
      }
      return key;
    }

    function graphQLFetcher(params) {
      return fetch(window.location.pathname, {
        method: 'post',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + apiKey()
        },
        body: JSON.stringify(params),
        credentials: 'omit'
      }).then(function (response) {
        if (response.status === 401) {
          window.sessionStorage.removeItem(KEY_NAME);
        }
        return response.json();
      });
    }

    ReactDOM.render(
      React.createElement(GraphiQL, {fetcher: graphQLFetcher}),
      document.body
    );
  </script>
</body>
</html>
'''
