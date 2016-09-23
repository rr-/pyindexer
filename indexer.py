def application(env, start_response):
    for key, value in env.items():
        print(key, value)
    print(env['PATH_INFO'])
    start_response('200 OK', [('Content-Type','text/html')])
    return [b"Hello World"]
