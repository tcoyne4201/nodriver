# Copyright 2024 by UltrafunkAmsterdam (https://github.com/UltrafunkAmsterdam)
# All rights reserved.
# This file is part of the nodriver package.
# and is released under the "GNU AFFERO GENERAL PUBLIC LICENSE".
# Please see the LICENSE.txt file that should have been included as part of this package.

from __future__ import annotations

import asyncio
import functools
import logging
import os
import pathlib
import secrets
import typing
import warnings
from pathlib import Path
from typing import Any, Generator, List, Optional, Tuple, Union

import nodriver.core.browser

from .. import cdp
from . import element, util
from .config import PathLike
from .connection import Connection, ProtocolException

logger = logging.getLogger(__name__)


class Tab(Connection):
    """
    :ref:`tab` is the controlling mechanism/connection to a 'target',
    for most of us 'target' can be read as 'tab'. however it could also
    be an iframe, serviceworker or background script for example,
    although there isn't much to control for those.

    if you open a new window by using :py:meth:`browser.get(..., new_window=True)`
    your url will open a new window. this window is a 'tab'.
    When you browse to another page, the tab will be the same (it is an browser view).

    So it's important to keep some reference to tab objects, in case you're
    done interacting with elements and want to operate on the page level again.

    Custom CDP commands
    ---------------------------
    Tab object provide many useful and often-used methods. It is also
    possible to utilize the included cdp classes to to something totally custom.

    the cdp package is a set of so-called "domains" with each having methods, events and types.
    to send a cdp method, for example :py:obj:`cdp.page.navigate`, you'll have to check
    whether the method accepts any parameters and whether they are required or not.

    you can use

    ```python
    await tab.send(cdp.page.navigate(url='https://yoururlhere'))
    ```

    so tab.send() accepts a generator object, which is created by calling a cdp method.
    this way you can build very detailed and customized commands.
    (note: finding correct command combo's can be a time consuming task, luckily i added a whole bunch
    of useful methods, preferably having the same api's or lookalikes, as in selenium)


    some useful, often needed and simply required methods
    ===================================================================


    :py:meth:`~find`  |  find(text)
    ----------------------------------------
    find and returns a single element by text match. by default returns the first element found.
    much more powerful is the best_match flag, although also much more expensive.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~find` |  find(text, best_match=True) or find(text, True)
    ---------------------------------------------------------------------------------
    Much more powerful (and expensive!!) than the above, is the use of the `find(text, best_match=True)` flag.
    It will still return 1 element, but when multiple matches are found, picks the one having the
    most similar text length.
    How would that help?
    For example, you search for "login", you'd probably want the "login" button element,
    and not thousands of scripts,meta,headings which happens to contain a string of "login".

    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select` | select(selector)
    ----------------------------------------
    find and returns a single element by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    :py:meth:`~select_all` | select_all(selector)
    ------------------------------------------------
    find and returns all elements by css selector match.
    when no match is found, it will retry for <timeout> seconds (default: 10), so
    this is also suitable to use as wait condition.


    await :py:obj:`Tab`
    ---------------------------
    calling `await tab` will do a lot of stuff under the hood, and ensures all references
    are up to date. also it allows for the script to "breathe", as it is oftentime faster than your browser or
    webpage. So whenever you get stuck and things crashes or element could not be found, you should probably let
    it "breathe"  by calling `await page`  and/or `await page.sleep()`

    also, it's ensuring :py:obj:`~url` will be updated to the most recent one, which is quite important in some
    other methods.

    attempts to find the location of given template image in the current viewport
    the only real use case for this is bot-detection systems.
    you can find for example the location of a 'verify'-checkbox,
    which are hidden from dom using shadow-root's or workers.



    await :py:obj:`Tab.template_location` (and await :py:obj:`Tab.verify_cf`)
    ------------------------------------------------------------------------------

    attempts to find the location of given template image in the current viewport.
    the only real use case for this is bot-detection systems.
    you can find, for example the location of a ‘verify’-checkbox, which are hidden from dom
    using shadow-root’s or/or workers and cannot be controlled by normal methods.

    template_image can be custom (for example your language, included is english only),
    but you need to create the template image yourself, which is just a cropped
    image of the area, see example image, where the target is exactly in the center.
    template_image can be custom (for example your language), but you need to
    create the template image yourself, where the target is exactly in the center.


    example (111x71)
    ---------
    this includes the white space on the left, to make the box center

    .. image:: template_example.png
        :width: 111
        :alt: example template image


    Using other and custom CDP commands
    ======================================================
    using the included cdp module, you can easily craft commands, which will always return an generator object.
    this generator object can be easily sent to the :py:meth:`~send`  method.

    :py:meth:`~send`
    ---------------------------
    this is probably THE most important method, although you won't ever call it, unless you want to
    go really custom. the send method accepts a :py:obj:`cdp` command. Each of which can be found in the
    cdp section.

    when you import * from this package, cdp will be in your namespace, and contains all domains/actions/events
    you can act upon.
    """

    browser: nodriver.core.browser.Browser
    _download_behavior: List[str] = None

    def __init__(
        self,
        websocket_url: str,
        target: cdp.target.TargetInfo,
        browser: Optional["nodriver.Browser"] = None,
        **kwargs,
    ):
        super().__init__(websocket_url, target, browser, **kwargs)
        self._dom = None
        self._window_id = None

    @property
    def inspector_url(self):
        """
        get the inspector url. this url can be used in another browser to show you the devtools interface for
        current tab. useful for debugging (and headless)
        :return:
        :rtype:
        """
        return f"http://{self.browser.config.host}:{self.browser.config.port}/devtools/inspector.html?ws={self.websocket_url[5:]}"

    def inspector_open(self):
        import webbrowser

        webbrowser.open(self.inspector_url, new=2)

    async def open_external_inspector(self):
        """
        opens the system's browser containing the devtools inspector page
        for this tab. could be handy, especially to debug in headless mode.
        """
        import webbrowser

        webbrowser.open(self.inspector_url)

    async def feed_cdp(
        self, cmd: Generator[dict[str, Any], dict[str, Any], Any]
    ) -> asyncio.Future:
        return await super()._send_oneshot(cmd)

    async def _prepare_headless(self):

        if getattr(self, "_prep_headless_done", None):
            return
        resp = await self._send_oneshot(
            cdp.runtime.evaluate(
                expression="navigator.userAgent",
            )
        )
        if not resp:
            return
        response, error = resp
        if response and response.value:
            ua = response.value
            await self._send_oneshot(
                cdp.network.set_user_agent_override(
                    user_agent=ua.replace("Headless", ""),
                )
            )
        setattr(self, "_prep_headless_done", True)

    async def _prepare_expert(self):
        if getattr(self, "_prep_expert_done", None):
            return
        if self.browser:
            await self._send_oneshot(cdp.page.enable())
            await self._send_oneshot(
                cdp.page.add_script_to_evaluate_on_new_document(
                    """
                    console.log("hooking attachShadow");
                    Element.prototype._attachShadow = Element.prototype.attachShadow;
                    Element.prototype.attachShadow = function () {
                        console.log('calling hooked attachShadow')
                        return this._attachShadow( { mode: "open" } );
                    };"""
                )
            )

        setattr(self, "_prep_expert_done", True)

    async def find(
        self,
        text: str,
        best_match: bool = True,
        return_enclosing_element=True,
        timeout: Union[int, float] = 10,
    ):
        """
        find single element by text
        can also be used to wait for such element to appear.

        :param text: text to search for. note: script contents are also considered text
        :type text: str
        :param best_match:  :param best_match:  when True (default), it will return the element which has the most
                                               comparable string length. this could help tremendously, when for example
                                               you search for "login", you'd probably want the login button element,
                                               and not thousands of scripts,meta,headings containing a string of "login".
                                               When False, it will return naively just the first match (but is way faster).
         :type best_match: bool
         :param return_enclosing_element:
                 since we deal with nodes instead of elements, the find function most often returns
                 so called text nodes, which is actually a element of plain text, which is
                 the somehow imaginary "child" of a "span", "p", "script" or any other elements which have text between their opening
                 and closing tags.
                 most often when we search by text, we actually aim for the element containing the text instead of
                 a lousy plain text node, so by default the containing element is returned.

                 however, there are (why not) exceptions, for example elements that use the "placeholder=" property.
                 this text is rendered, but is not a pure text node. in that case you can set this flag to False.
                 since in this case we are probably interested in just that element, and not it's parent.


                 # todo, automatically determine node type
                 # ignore the return_enclosing_element flag if the found node is NOT a text node but a
                 # regular element (one having a tag) in which case that is exactly what we need.
         :type return_enclosing_element: bool
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        text = text.strip()

        item = await self.find_element_by_text(
            text, best_match, return_enclosing_element
        )
        while not item:
            await self
            item = await self.find_element_by_text(
                text, best_match, return_enclosing_element
            )
            if loop.time() - start_time > timeout:
                return item
            await self.sleep(0.5)
        return item

    async def select(
        self,
        selector: str,
        timeout: Union[int, float] = 10,
    ) -> nodriver.Element:
        """
        find single element by css selector.
        can also be used to wait for such element to appear.

        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int

        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()

        selector = selector.strip()
        item = await self.query_selector(selector)

        while not item:
            await self
            item = await self.query_selector(selector)
            if loop.time() - start_time > timeout:
                return item
            await self.sleep(0.5)
        return item

    async def find_all(
        self,
        text: str,
        timeout: Union[int, float] = 10,
    ) -> List[nodriver.Element]:
        """
        find multiple elements by text
        can also be used to wait for such element to appear.

        :param text: text to search for. note: script contents are also considered text
        :type text: str

        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        """
        loop = asyncio.get_running_loop()
        now = loop.time()

        text = text.strip()
        items = await self.find_elements_by_text(text)

        while not items:
            await self
            items = await self.find_elements_by_text(text)
            if loop.time() - now > timeout:
                return items
            await self.sleep(0.5)
        return items

    async def select_all(
        self, selector: str, timeout: Union[int, float] = 10, include_frames=False
    ) -> List[nodriver.Element]:
        """
        find multiple elements by css selector.
        can also be used to wait for such element to appear.


        :param selector: css selector, eg a[href], button[class*=close], a > img[src]
        :type selector: str
        :param timeout: raise timeout exception when after this many seconds nothing is found.
        :type timeout: float,int
        :param include_frames: whether to include results in iframes.
        :type include_frames: bool
        """
        loop = asyncio.get_running_loop()
        now = loop.time()
        selector = selector.strip()
        items = []
        if include_frames:
            frames = await self.query_selector_all("iframe")
            # unfortunately, asyncio.gather here is not an option
            for fr in frames:
                items.extend(await fr.query_selector_all(selector))

        items.extend(await self.query_selector_all(selector))
        while not items:
            await self
            items = await self.query_selector_all(selector)
            if loop.time() - now > timeout:
                return items
            await self.sleep(0.5)
        return items

    async def sleep(self, t: float | int = 1):
        if self.browser:
            await asyncio.wait(
                [
                    asyncio.create_task(self.browser.update_targets()),
                    asyncio.create_task(asyncio.sleep(t)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

    async def xpath(
        self, xpath: str, timeout: float = 2.5
    ) -> List[Optional[nodriver.Element]]:  # noqa
        """
        find elements by xpath string.
        if not immediately found, retries are attempted until :ref:`timeout` is reached (default 2.5 seconds).
        in case nothing is found, it returns an empty list. It will not raise.
        this timeout mechanism helps when relying on some element to appear before continuing your script.


        .. code-block:: python

             # find all the inline scripts (script elements without src attribute )
             await tab.xpath('//script[not(@src)]')

             # or here, more complex, but my personal favorite to case-insensitive text search

             await tab.xpath('//text()[ contains( translate(., "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"),"test")]')


        :param xpath:
        :type xpath: str
        :param timeout: 2.5
        :type timeout: float
        :return:List[nodriver.Element] or []
        :rtype:
        """
        items: List[Optional[nodriver.Element]] = []
        try:
            await self.send(cdp.dom.enable(), True)
            items = await self.find_all(xpath, timeout=0)
            if not items:
                loop = asyncio.get_running_loop()
                start_time = loop.time()
                while not items:
                    items = await self.find_all(xpath, timeout=0)
                    await self.sleep(0.1)
                    if loop.time() - start_time > timeout:
                        break
        finally:
            try:
                await self.send(cdp.dom.disable(), True)
            except ProtocolException:
                # for some strange reason, the call to dom.disable
                # sometimes raises an exception that dom is not enabled.
                pass
        return items

    async def get(
        self, url="chrome://welcome", new_tab: bool = False, new_window: bool = False
    ):
        """top level get. utilizes the first tab to retrieve given url.

        convenience function known from selenium.
        this function handles waits/sleeps and detects when DOM events fired, so it's the safest
        way of navigating.

        :param url: the url to navigate to
        :param new_tab: open new tab
        :param new_window:  open new window
        :return: Page
        """
        if not self.browser:
            raise AttributeError(
                "this page/tab has no browser attribute, so you can't use get()"
            )
        if new_window and not new_tab:
            new_tab = True

        if new_tab:
            return await self.browser.get(url, new_tab, new_window)
        else:
            frame_id, loader_id, *_ = await self.send(cdp.page.navigate(url))
            await self
            return self

    async def query_selector_all(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, "element.Element"]] = None,
    ):
        """
        equivalent of javascripts document.querySelectorAll.
        this is considered one of the main methods to use in this package.

        it returns all matching :py:obj:`nodriver.Element` objects.

        :param selector: css selector. (first time? => https://www.w3schools.com/cssref/css_selectors.php )
        :type selector: str
        :param _node: internal use
        :type _node:
        :return:
        :rtype:
        """

        if not _node:
            doc: cdp.dom.Node = await self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document

        node_ids = []

        try:
            node_ids = await self.send(
                cdp.dom.query_selector_all(doc.node_id, selector)
            )
        except AttributeError:
            # has no content_document
            return

        except ProtocolException as e:
            if _node is not None:
                if "could not find node" in e.message.lower():
                    if getattr(_node, "__last", None):
                        del _node.__last
                        return []
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    await _node.update()
                    _node.__last = (
                        True  # make sure this isn't turned into infinite loop
                    )
                    return await self.query_selector_all(selector, _node)
            else:
                await self.send(cdp.dom.disable())
                raise
        if not node_ids:
            return []
        items = []

        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            # we pass along the retrieved document tree,
            # to improve performance
            if not node:
                continue
            elem = element.create(node, self, doc)
            items.append(elem)

        return items

    async def query_selector(
        self,
        selector: str,
        _node: Optional[Union[cdp.dom.Node, element.Element]] = None,
    ):
        """
        find single element based on css selector string

        :param selector: css selector(s)
        :type selector: str
        :return:
        :rtype:
        """
        selector = selector.strip()

        if not _node:
            doc: cdp.dom.Node = await self.send(cdp.dom.get_document(-1, True))
        else:
            doc = _node
            if _node.node_name == "IFRAME":
                doc = _node.content_document
        node_id = None

        try:
            node_id = await self.send(cdp.dom.query_selector(doc.node_id, selector))

        except ProtocolException as e:
            if _node is not None:
                if "could not find node" in e.message.lower():
                    if getattr(_node, "__last", None):
                        del _node.__last
                        return []
                    # if supplied node is not found, the dom has changed since acquiring the element
                    # therefore we need to update our passed node and try again
                    await _node.update()
                    _node.__last = (
                        True  # make sure this isn't turned into infinite loop
                    )
                    return await self.query_selector(selector, _node)
            else:
                await self.send(cdp.dom.disable())
                raise
        if not node_id:
            return
        node = util.filter_recurse(doc, lambda n: n.node_id == node_id)
        if not node:
            return
        return element.create(node, self, doc)

    async def find_elements_by_text(
        self,
        text: str,
        tag_hint: Optional[str] = None,
    ) -> List[element.Element]:
        """
        returns element which match the given text.
        returns element which match the given text.
        please note: this may (or will) also return any other element (like inline scripts),
        which happen to contain that text.

        :param text:
        :type text:
        :param tag_hint: when provided, narrows down search to only elements which match given tag eg: a, div, script, span
        :type tag_hint: str
        :return:
        :rtype:
        """
        text = text.strip()
        doc = await self.send(cdp.dom.get_document(-1, True))
        search_id, nresult = await self.send(cdp.dom.perform_search(text, True))
        if nresult:
            node_ids = await self.send(
                cdp.dom.get_search_results(search_id, 0, nresult)
            )
        else:
            node_ids = []

        await self.send(cdp.dom.discard_search_results(search_id))

        items = []
        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            if not node:
                node = await self.send(cdp.dom.resolve_node(node_id=nid))
                if not node:
                    continue
                # remote_object = await self.send(cdp.dom.resolve_node(backend_node_id=node.backend_node_id))
                # node_id = await self.send(cdp.dom.request_node(object_id=remote_object.object_id))
            try:
                elem = element.create(node, self, doc)
            except:  # noqa
                continue
            if elem.node_type == 3:
                # if found element is a text node (which is plain text, and useless for our purpose),
                # we return the parent element of the node (which is often a tag which can have text between their
                # opening and closing tags (that is most tags, except for example "img" and "video", "br")

                if not elem.parent:
                    # check if parent actually has a parent and update it to be absolutely sure
                    await elem.update()

                items.append(
                    elem.parent or elem
                )  # when it really has no parent, use the text node itself
                continue
            else:
                # just add the element itself
                items.append(elem)

        # since we already fetched the entire doc, including shadow and frames
        # let's also search through the iframes
        iframes = util.filter_recurse_all(doc, lambda node: node.node_name == "IFRAME")
        if iframes:
            iframes_elems = [
                element.create(iframe, self, iframe.content_document)
                for iframe in iframes
            ]
            for iframe_elem in iframes_elems:
                if iframe_elem.content_document:
                    iframe_text_nodes = util.filter_recurse_all(
                        iframe_elem,
                        lambda node: node.node_type == 3  # noqa
                        and text.lower() in node.node_value.lower(),
                    )
                    if iframe_text_nodes:
                        iframe_text_elems = [
                            element.create(text_node, self, iframe_elem.tree)
                            for text_node in iframe_text_nodes
                        ]
                        items.extend(
                            text_node.parent for text_node in iframe_text_elems
                        )
        await self.send(cdp.dom.disable())
        return items or []

    async def find_element_by_text(
        self,
        text: str,
        best_match: Optional[bool] = False,
        return_enclosing_element: Optional[bool] = True,
    ) -> Union[element.Element, None]:
        """
        finds and returns the first element containing <text>, or best match

        :param text:
        :type text:
        :param best_match:  when True, which is MUCH more expensive (thus much slower),
                            will find the closest match based on length.
                            this could help tremendously, when for example you search for "login", you'd probably want the login button element,
                            and not thousands of scripts,meta,headings containing a string of "login".

        :type best_match: bool
        :param return_enclosing_element:
        :type return_enclosing_element:
        :return:
        :rtype:
        """
        doc = await self.send(cdp.dom.get_document(-1, True))
        text = text.strip()
        search_id, nresult = await self.send(cdp.dom.perform_search(text, True))
        if nresult:
            node_ids = await self.send(
                cdp.dom.get_search_results(search_id, 0, nresult)
            )
        else:
            node_ids = None
        await self.send(cdp.dom.discard_search_results(search_id))
        if not node_ids:
            node_ids = []
        items = []
        for nid in node_ids:
            node = util.filter_recurse(doc, lambda n: n.node_id == nid)
            try:
                elem = element.create(node, self, doc)
            except:  # noqa
                continue
            if elem.node_type == 3:
                # if found element is a text node (which is plain text, and useless for our purpose),
                # we return the parent element of the node (which is often a tag which can have text between their
                # opening and closing tags (that is most tags, except for example "img" and "video", "br")

                if not elem.parent:
                    # check if parent actually has a parent and update it to be absolutely sure
                    await elem.update()

                items.append(
                    elem.parent or elem
                )  # when it really has no parent, use the text node itself
                continue
            else:
                # just add the element itself
                items.append(elem)

        # since we already fetched the entire doc, including shadow and frames
        # let's also search through the iframes
        iframes = util.filter_recurse_all(doc, lambda node: node.node_name == "IFRAME")
        if iframes:
            iframes_elems = [
                element.create(iframe, self, iframe.content_document)
                for iframe in iframes
            ]
            for iframe_elem in iframes_elems:
                iframe_text_nodes = util.filter_recurse_all(
                    iframe_elem,
                    lambda node: node.node_type == 3  # noqa
                    and text.lower() in node.node_value.lower(),
                )
                if iframe_text_nodes:
                    iframe_text_elems = [
                        element.create(text_node, self, iframe_elem.tree)
                        for text_node in iframe_text_nodes
                    ]
                    items.extend(text_node.parent for text_node in iframe_text_elems)

        try:
            if not items:
                return
            if best_match:
                closest_by_length = min(
                    items, key=lambda el: abs(len(text) - len(el.text_all))
                )
                elem = closest_by_length or items[0]

                return elem
            else:
                # naively just return the first result
                for elem in items:
                    if elem:
                        return elem
        finally:
            await self.send(cdp.dom.disable())

    async def back(self):
        """
        history back
        """
        await self.send(cdp.runtime.evaluate("window.history.back()"))

    async def forward(self):
        """
        history forward
        """
        await self.send(cdp.runtime.evaluate("window.history.forward()"))

    async def reload(
        self,
        ignore_cache: Optional[bool] = True,
        script_to_evaluate_on_load: Optional[str] = None,
    ):
        """
        Reloads the page

        :param ignore_cache: when set to True (default), it ignores cache, and re-downloads the items
        :type ignore_cache:
        :param script_to_evaluate_on_load: script to run on load. I actually haven't experimented with this one, so no guarantees.
        :type script_to_evaluate_on_load:
        :return:
        :rtype:
        """
        await self.send(
            cdp.page.reload(
                ignore_cache=ignore_cache,
                script_to_evaluate_on_load=script_to_evaluate_on_load,
            ),
        )

    async def evaluate(
        self, expression: str, await_promise=False, return_by_value=False
    ) -> Union[
        str,
        Union[str, Any],
        Tuple[cdp.runtime.RemoteObject, cdp.runtime.ExceptionDetails | None],
    ]:

        ser = cdp.runtime.SerializationOptions(
            serialization="deep",
            max_depth=10,
            additional_parameters={"maxNodeDepth": 10, "includeShadowTree": "all"},
        )
        remote_object: cdp.runtime.RemoteObject = None
        errors: cdp.runtime.ExceptionDetails = None

        remote_object, errors = await self.send(
            cdp.runtime.evaluate(
                expression=expression,
                user_gesture=True,
                await_promise=await_promise,
                return_by_value=return_by_value,
                allow_unsafe_eval_blocked_by_csp=True,
                serialization_options=ser,
            )
        )
        if errors:
            return errors
        if remote_object:
            if return_by_value:
                if remote_object.value:
                    return remote_object.value
            else:
                if remote_object.deep_serialized_value:
                    return remote_object.deep_serialized_value.value

        return remote_object

    async def js_dumps(
        self, obj_name: str, return_by_value: Optional[bool] = True
    ) -> typing.Union[
        typing.Dict,
        typing.Tuple[cdp.runtime.RemoteObject, cdp.runtime.ExceptionDetails],
    ]:
        """
        dump given js object with its properties and values as a dict

        note: complex objects might not be serializable, therefore this method is not a "source of thruth"

        :param obj_name: the js object to dump
        :type obj_name: str

        :param return_by_value: if you want an tuple of cdp objects (returnvalue, errors), set this to False
        :type return_by_value: bool

        example
        ------

        x = await self.js_dumps('window')
        print(x)
            '...{
            'pageYOffset': 0,
            'visualViewport': {},
            'screenX': 10,
            'screenY': 10,
            'outerWidth': 1050,
            'outerHeight': 832,
            'devicePixelRatio': 1,
            'screenLeft': 10,
            'screenTop': 10,
            'styleMedia': {},
            'onsearch': None,
            'isSecureContext': True,
            'trustedTypes': {},
            'performance': {'timeOrigin': 1707823094767.9,
            'timing': {'connectStart': 0,
            'navigationStart': 1707823094768,
            ]...
            '
        """
        js_code_a = (
            """
                                                   function ___dump(obj, _d = 0) {
                                                       let _typesA = ['object', 'function'];
                                                       let _typesB = ['number', 'string', 'boolean'];
                                                       if (_d == 2) {
                                                           // console.log('maxdepth reached for ', obj);
                                                           return
                                                       }
                                                       let tmp = {}
                                                       for (let k in obj) {
                                                           if (obj[k] == window) continue;
                                                           let v;
                                                           try {
                                                               if (obj[k] === null || obj[k] === undefined || obj[k] === NaN) {
                                                                    // console.log('obj[k] is null or undefined or Nan', k, '=>', obj[k])
                                                                   tmp[k] = obj[k];
                                                                   continue
                                                               }
                                                           } catch (e) {
                                                               tmp[k] = null;
                                                               continue
                                                           }
                        
                                                           if (_typesB.includes(typeof obj[k])) {
                                                               tmp[k] = obj[k]
                                                               continue
                                                           }
                        
                                                           try {
                                                               if (typeof obj[k] === 'function') {
                                                                   tmp[k] = obj[k].toString()
                                                                   continue
                                                               }
                        
                        
                                                               if (typeof obj[k] === 'object') {
                                                                   tmp[k] = ___dump(obj[k], _d + 1);
                                                                   continue
                                                               }
                        
                        
                                                           } catch (e) {}
                        
                                                           try {
                                                               tmp[k] = JSON.stringify(obj[k])
                                                               continue
                                                           } catch (e) {
                        
                                                           }
                                                           try {
                                                               tmp[k] = obj[k].toString();
                                                               continue
                                                           } catch (e) {}
                                                       }
                                                       return tmp
                                                   }
                        
                                                   function ___dumpY(obj) {
                                                       var objKeys = (obj) => {
                                                           var [target, result] = [obj, []];
                                                           while (target !== null) {
                                                               result = result.concat(Object.getOwnPropertyNames(target));
                                                               target = Object.getPrototypeOf(target);
                                                           }
                                                           return result;
                                                       }
                                                       return Object.fromEntries(
                                                           objKeys(obj).map(_ => [_, ___dump(obj[_])]))
                        
                                                   }
                                                   ___dumpY( %s )
                                           """
            % obj_name
        )
        js_code_b = (
            """
                                    ((obj, visited = new WeakSet()) => {
                                         if (visited.has(obj)) {
                                             return {}
                                         }
                                         visited.add(obj)
                                         var result = {}, _tmp;
                                         for (var i in obj) {
                                                 try {
                                                     if (i === 'enabledPlugin' || typeof obj[i] === 'function') {
                                                         continue;
                                                     } else if (typeof obj[i] === 'object') {
                                                         _tmp = recurse(obj[i], visited);
                                                         if (Object.keys(_tmp).length) {
                                                             result[i] = _tmp;
                                                         }
                                                     } else {
                                                         result[i] = obj[i];
                                                     }
                                                 } catch (error) {
                                                     // console.error('Error:', error);
                                                 }
                                             }
                                        return result;
                                    })(%s)
                                """
            % obj_name
        )

        # we're purposely not calling self.evaluate here to prevent infinite loop on certain expressions

        remote_object, exception_details = await self.send(
            cdp.runtime.evaluate(
                js_code_a,
                await_promise=True,
                return_by_value=return_by_value,
                allow_unsafe_eval_blocked_by_csp=True,
            )
        )
        if exception_details:
            # try second variant

            remote_object, exception_details = await self.send(
                cdp.runtime.evaluate(
                    js_code_b,
                    await_promise=True,
                    return_by_value=return_by_value,
                    allow_unsafe_eval_blocked_by_csp=True,
                )
            )

        if exception_details:
            raise ProtocolException(exception_details)
        if return_by_value:
            if remote_object.value:
                return remote_object.value
        else:
            return remote_object, exception_details

    async def close(self):
        """
        close the current target (ie: tab,window,page)
        :return:
        :rtype:
        """
        if self.target and self.target.target_id:
            await self.send(cdp.target.close_target(target_id=self.target.target_id))

    async def get_window(self) -> Tuple[cdp.browser.WindowID, cdp.browser.Bounds]:
        """
        get the window Bounds
        :return:
        :rtype:
        """
        window_id, bounds = await self.send(
            cdp.browser.get_window_for_target(self.target_id)
        )
        return window_id, bounds

    async def get_content(self):
        """
        gets the current page source content (html)
        :return:
        :rtype:
        """
        doc: cdp.dom.Node = await self.send(cdp.dom.get_document(-1, True))
        return await self.send(
            cdp.dom.get_outer_html(backend_node_id=doc.backend_node_id)
        )

    async def maximize(self):
        """
        maximize page/tab/window
        """
        return await self.set_window_state(state="maximize")

    async def minimize(self):
        """
        minimize page/tab/window
        """
        return await self.set_window_state(state="minimize")

    async def fullscreen(self):
        """
        minimize page/tab/window
        """
        return await self.set_window_state(state="fullscreen")

    async def medimize(self):
        return await self.set_window_state(state="normal")

    async def set_window_size(self, left=0, top=0, width=1280, height=1024):
        """
        set window size and position

        :param left: pixels from the left of the screen to the window top-left corner
        :type left:
        :param top: pixels from the top of the screen to the window top-left corner
        :type top:
        :param width: width of the window in pixels
        :type width:
        :param height: height of the window in pixels
        :type height:
        :return:
        :rtype:
        """
        return await self.set_window_state(left, top, width, height)

    async def activate(self):
        """
        active this target (ie: tab,window,page)
        """
        await self.send(cdp.target.activate_target(self.target.target_id))

    async def bring_to_front(self):
        """
        alias to self.activate
        """
        await self.activate()

    async def set_window_state(
        self, left=0, top=0, width=1280, height=720, state="normal"
    ):
        """
        sets the window size or state.

        for state you can provide the full name like minimized, maximized, normal, fullscreen, or
        something which leads to either of those, like min, mini, mi,  max, ma, maxi, full, fu, no, nor
        in case state is set other than "normal", the left, top, width, and height are ignored.

        :param left:
            desired offset from left, in pixels
        :type left: int

        :param top:
            desired offset from the top, in pixels
        :type top: int

        :param width:
            desired width in pixels
        :type width: int

        :param height:
            desired height in pixels
        :type height: int

        :param state:
            can be one of the following strings:
                - normal
                - fullscreen
                - maximized
                - minimized

        :type state: str

        """
        available_states = ["minimized", "maximized", "fullscreen", "normal"]
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        for state_name in available_states:
            if all(x in state_name for x in state.lower()):
                break
        else:
            raise NameError(
                "could not determine any of %s from input '%s'"
                % (",".join(available_states), state)
            )
        window_state = getattr(
            cdp.browser.WindowState, state_name.upper(), cdp.browser.WindowState.NORMAL
        )
        if window_state == cdp.browser.WindowState.NORMAL:
            bounds = cdp.browser.Bounds(left, top, width, height, window_state)
        else:
            # min, max, full can only be used when current state == NORMAL
            # therefore we first switch to NORMAL
            await self.set_window_state(state="normal")
            bounds = cdp.browser.Bounds(window_state=window_state)

        await self.send(cdp.browser.set_window_bounds(window_id, bounds=bounds))

    async def scroll_down(self, amount=25):
        """
        scrolls down maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int
        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        await self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=-(bounds.height * (amount / 100)),
                y_overscroll=0,
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    async def scroll_up(self, amount=25):
        """
        scrolls up maybe

        :param amount: number in percentage. 25 is a quarter of page, 50 half, and 1000 is 10x the page
        :type amount: int

        :return:
        :rtype:
        """
        window_id: cdp.browser.WindowID
        bounds: cdp.browser.Bounds
        (window_id, bounds) = await self.get_window()

        await self.send(
            cdp.input_.synthesize_scroll_gesture(
                x=0,
                y=0,
                y_distance=(bounds.height * (amount / 100)),
                x_overscroll=0,
                prevent_fling=True,
                repeat_delay_ms=0,
                speed=7777,
            )
        )

    async def wait(self, t: Union[int, float] = None):

        # await self.browser.wait()

        loop = asyncio.get_running_loop()
        start = loop.time()
        event = asyncio.Event()
        wait_events = [
            cdp.page.FrameStoppedLoading,
            cdp.page.FrameDetached,
            cdp.page.FrameNavigated,
            cdp.page.LifecycleEvent,
            cdp.page.LoadEventFired,
        ]

        handler = lambda ev: event.set()

        self.add_handler(wait_events, handler=handler)
        try:
            if not t:
                t = 0.5
            done, pending = await asyncio.wait(
                [
                    asyncio.ensure_future(event.wait()),
                    asyncio.ensure_future(asyncio.sleep(t)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

            [p.cancel() for p in pending]

        finally:
            self.remove_handler(wait_events, handler=handler)
        #         await asyncio.wait_for()
        #     except asyncio.TimeoutError:
        #         if isinstance(t, (int, float)):
        #             # explicit time is given, which is now passed
        #             # so bail out early
        #             return

    def __await__(self):
        return self.wait().__await__()

    async def wait_for(
        self,
        selector: Optional[str] = "",
        text: Optional[str] = "",
        timeout: Optional[Union[int, float]] = 10,
    ) -> element.Element:
        """
        variant on query_selector_all and find_elements_by_text
        this variant takes either selector or text, and will block until
        the requested element(s) are found.

        it will block for a maximum of <timeout> seconds, after which
        an TimeoutError will be raised

        :param selector: css selector
        :type selector:
        :param text: text
        :type text:
        :param timeout:
        :type timeout:
        :return:
        :rtype: Element
        :raises: asyncio.TimeoutError
        """
        loop = asyncio.get_running_loop()
        now = loop.time()
        if selector:
            item = await self.query_selector(selector)
            while not item:
                item = await self.query_selector(selector)
                if loop.time() - now > timeout:
                    raise asyncio.TimeoutError(
                        "time ran out while waiting for %s" % selector
                    )
                await self.sleep(0.5)
                # await self.sleep(0.5)
            return item
        if text:
            item = await self.find_element_by_text(text)
            while not item:
                item = await self.find_element_by_text(text)
                if loop.time() - now > timeout:
                    raise asyncio.TimeoutError(
                        "time ran out while waiting for text: %s" % text
                    )
                await self.sleep(0.5)
            return item

    async def download_file(self, url: str, filename: Optional[PathLike] = None):
        """
        downloads file by given url.

        :param url: url of the file
        :param filename: the name for the file. if not specified the name is composed from the url file name
        """
        if not self._download_behavior:
            directory_path = pathlib.Path.cwd() / "downloads"
            directory_path.mkdir(exist_ok=True)
            await self.set_download_path(directory_path)

            warnings.warn(
                f"no download path set, so creating and using a default of"
                f"{directory_path}"
            )
        if not filename:
            filename = url.rsplit("/")[-1]
            filename = filename.split("?")[0]

        code = """
         (elem) => {
            async function _downloadFile(
              imageSrc,
              nameOfDownload,
            ) {
              const response = await fetch(imageSrc);
              const blobImage = await response.blob();
              const href = URL.createObjectURL(blobImage);

              const anchorElement = document.createElement('a');
              anchorElement.href = href;
              anchorElement.download = nameOfDownload;

              document.body.appendChild(anchorElement);
              anchorElement.click();

              setTimeout(() => {
                document.body.removeChild(anchorElement);
                window.URL.revokeObjectURL(href);
                }, 500);
            }
            _downloadFile('%s', '%s')
            }
            """ % (
            url,
            filename,
        )

        body = (await self.query_selector_all("body"))[0]
        await body.update()
        await self.send(
            cdp.runtime.call_function_on(
                code,
                object_id=body.object_id,
                arguments=[cdp.runtime.CallArgument(object_id=body.object_id)],
            )
        )
        await self.wait(0.1)

    async def save_screenshot(
        self,
        filename: Optional[PathLike] = "auto",
        format: Optional[str] = "jpeg",
        full_page: Optional[bool] = False,
    ) -> str:
        """
        Saves a screenshot of the page.
        This is not the same as :py:obj:`Element.save_screenshot`, which saves a screenshot of a single element only

        :param filename: uses this as the save path
        :type filename: PathLike
        :param format: jpeg or png (defaults to jpeg)
        :type format: str
        :param full_page: when False (default) it captures the current viewport. when True, it captures the entire page
        :type full_page: bool
        :return: the path/filename of saved screenshot
        :rtype: str
        """
        # noqa
        import datetime
        import urllib.parse

        await self.sleep()  # update the target's url
        path = None

        if format.lower() in ["jpg", "jpeg"]:
            ext = ".jpg"
            format = "jpeg"

        elif format.lower() in ["png"]:
            ext = ".png"
            format = "png"

        if not filename or filename == "auto":
            parsed = urllib.parse.urlparse(self.target.url)
            parts = parsed.path.split("/")
            last_part = parts[-1]
            last_part = last_part.rsplit("?", 1)[0]
            dt_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            candidate = f"{parsed.hostname}__{last_part}_{dt_str}"
            path = pathlib.Path(candidate + ext)  # noqa
        else:
            path = pathlib.Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = await self.send(
            cdp.page.capture_screenshot(
                format_=format, capture_beyond_viewport=full_page
            )
        )
        if not data:
            raise ProtocolException(
                "could not take screenshot. most possible cause is the page has not finished loading yet."
            )
        import base64

        data_bytes = base64.b64decode(data)
        if not path:
            raise RuntimeError("invalid filename or path: '%s'" % filename)
        path.write_bytes(data_bytes)
        return str(path)

    async def set_download_path(self, path: Union[str, PathLike]):
        """
        sets the download path and allows downloads
        this is required for any download function to work (well not entirely, since when unset we set a default folder)

        :param path:
        :type path:
        :return:
        :rtype:
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        await self.send(
            cdp.browser.set_download_behavior(
                behavior="allow", download_path=str(path.resolve())
            )
        )
        self._download_behavior = ["allow", str(path.resolve())]

    async def get_all_linked_sources(self) -> List["nodriver.Element"]:
        """
        get all elements of tag: link, a, img, scripts meta, video, audio

        :return:
        """
        all_assets = await self.query_selector_all(selector="a,link,img,script,meta")
        return [element.create(asset, self) for asset in all_assets]

    async def get_all_urls(self, absolute=True) -> List[str]:
        """
        convenience function, which returns all links (a,link,img,script,meta)

        :param absolute: try to build all the links in absolute form instead of "as is", often relative
        :return: list of urls
        """

        import urllib.parse

        res = []
        all_assets = await self.query_selector_all(selector="a,link,img,script,meta")
        for asset in all_assets:
            if not absolute:
                res.append(asset.src or asset.href)
            else:
                for k, v in asset.attrs.items():
                    if k in ("src", "href"):
                        if "#" in v:
                            continue
                        if not any([_ in v for _ in ("http", "//", "/")]):
                            continue
                        abs_url = urllib.parse.urljoin(
                            "/".join(self.url.rsplit("/")[:3]), v
                        )
                        if not abs_url.startswith(("http", "//", "ws")):
                            continue
                        res.append(abs_url)
        return res

    async def get_local_storage(self):
        """
        get local storage items as dict of strings (careful!, proper deserialization needs to be done if needed)

        :return:
        :rtype:
        """
        if not self.target.url:
            await self

        # there must be a better way...
        origin = "/".join(self.url.split("/", 3)[:-1])

        items = await self.send(
            cdp.dom_storage.get_dom_storage_items(
                cdp.dom_storage.StorageId(is_local_storage=True, security_origin=origin)
            )
        )
        retval = {}
        for item in items:
            retval[item[0]] = item[1]
        return retval

    async def set_local_storage(self, items: dict):
        """
        set local storage.
        dict items must be strings. simple types will be converted to strings automatically.

        :param items: dict containing {key:str, value:str}
        :type items: dict[str,str]
        :return:
        :rtype:
        """
        if not self.target.url:
            await self
        # there must be a better way...
        origin = "/".join(self.url.split("/", 3)[:-1])

        await asyncio.gather(
            *[
                self.send(
                    cdp.dom_storage.set_dom_storage_item(
                        storage_id=cdp.dom_storage.StorageId(
                            is_local_storage=True, security_origin=origin
                        ),
                        key=str(key),
                        value=str(val),
                    )
                )
                for key, val in items.items()
            ]
        )

    def __call__(
        self,
        text: Optional[str] = "",
        selector: Optional[str] = "",
        timeout: Optional[Union[int, float]] = 10,
    ):
        """
        alias to query_selector_all or find_elements_by_text, depending
        on whether text= is set or selector= is set

        :param selector: css selector string
        :type selector: str
        :return:
        :rtype:
        """
        return self.wait_for(text, selector, timeout)

    async def get_frame_tree(self) -> cdp.page.FrameTree:
        """
        retrieves the frame tree for current tab
        There seems no real difference between :ref:`Tab.get_frame_resource_tree()`
        :return:
        :rtype:
        """
        tree: cdp.page.FrameTree = await super().send(cdp.page.get_frame_tree())
        return tree

    async def get_frame_resource_tree(self) -> cdp.page.FrameResourceTree:
        """
        retrieves the frame resource tree for current tab.
        There seems no real difference between :ref:`Tab.get_frame_tree()`
        but still it returns a different object
        :return:
        :rtype:
        """
        tree: cdp.page.FrameResourceTree = await super().send(
            cdp.page.get_resource_tree()
        )
        return tree

    async def get_frame_resource_urls(self) -> List[str]:
        """
        gets the urls of resources
        :return:
        :rtype:
        """
        _tree = await self.get_frame_resource_tree()
        return [
            x
            for x in functools.reduce(
                lambda a, b: a + [b[1].url if isinstance(b, tuple) else ""],
                util.flatten_frame_tree_resources(_tree),
                [],
            )
            if x
        ]

    async def search_frame_resources(
        self, query: str
    ) -> typing.Dict[str, List[cdp.debugger.SearchMatch]]:
        try:
            await self._send_oneshot(cdp.page.enable())
            list_of_tuples = list(
                util.flatten_frame_tree_resources(await self.get_frame_resource_tree())
            )
            results = {}
            for item in list_of_tuples:
                if not isinstance(item, tuple):
                    continue
                frame, resource = item
                res = await self.send(
                    cdp.page.search_in_resource(
                        frame_id=frame.id_, url=resource.url, query=query
                    )
                )
                if not res:
                    continue
                results[resource.url] = res
        finally:
            await self._send_oneshot(cdp.page.disable())

        return results

    async def verify_cf(self, template_image: str = None, flash=False):
        """
        convenience function to verify cf checkbox

        template_image can be custom (for example your language, included is english only),
        but you need to create the template image yourself, which is just a cropped
        image of the area, see example image, where the target is exactly in the center.

        example (111x71)
        ---------
        this includes the white space on the left, to make the box center

        .. image:: template_example.png
            :width: 111
            :alt: example template image

        :param template_image:
            template_image can be custom (for example your language, included is english only),
            but you need to create the template image yourself, which is just a cropped
            image of the area, where the target is exactly in the center. see example on
            (https://ultrafunkamsterdam.github.io/nodriver/nodriver/classes/tab.html#example-111x71),

        :type template_image:
        :param flash: whether to show an indicator where the mouse is clicking.
        :type flash:
        :return:
        :rtype:
        """
        if self.browser and self.browser.config and self.browser.config.expert:
            raise Exception(
                """
                            this function is useless in expert mode, since it disables site-isolation-trials.
                            while this is a useful future to have access to all elements (also in iframes),
                            it is also being detected
                            """
            )
        x, y = await self.template_location(template_image=template_image)
        await self.mouse_click(x, y)
        if flash:
            await self.flash_point(x, y)

    async def template_location(
        self, template_image: PathLike = None
    ) -> Union[Tuple[int, int], None]:
        """
        attempts to find the location of given template image in the current viewport
        the only real use case for this is bot-detection systems.
        you can find for example the location of a 'verify'-checkbox,
        which are hidden from dom using shadow-root's or workers.

        template_image can be custom (for example your language, included is english only),
        but you need to create the template image yourself, which is just a cropped
        image of the area, see example image, where the target is exactly in the center.
        template_image can be custom (for example your language), but you need to
        create the template image yourself, where the target is exactly in the center.

        example (111x71)
        ---------
        this includes the white space on the left, to make the box center

        .. image:: template_example.png
            :width: 111
            :alt: example template image


        :param template_image:
        :type template_image:
        :return:
        :rtype:
        """
        try:
            import cv2
        except ImportError:
            logger.warning(
                """
                missing package
                ----------------
                template_location function needs the computer vision library "opencv-python" installed
                to install:
                pip install opencv-python
            
            """
            )
            return
        try:

            if template_image:
                template_image = Path(template_image)
                if not template_image.exists():
                    raise FileNotFoundError(
                        "%s was not found in the current location : %s"
                        % (template_image, os.getcwd())
                    )
            await self.save_screenshot("screen.jpg")
            await self.sleep(0.05)
            im = cv2.imread("screen.jpg")
            im_gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
            if template_image:
                template = cv2.imread(str(template_image))
            else:
                with open("cf_template.png", "w+b") as fh:
                    fh.write(util.get_cf_template())
                template = cv2.imread("cf_template.png")
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            match = cv2.matchTemplate(im_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            (min_v, max_v, min_l, max_l) = cv2.minMaxLoc(match)
            (xs, ys) = max_l
            tmp_h, tmp_w = template_gray.shape[:2]
            xe = xs + tmp_w
            ye = ys + tmp_h
            cx = (xs + xe) // 2
            cy = (ys + ye) // 2
            return cx, cy
        except (TypeError, OSError, PermissionError):
            pass  # ignore these exceptions
        except:  # noqa - don't ignore other exceptions
            raise
        finally:
            try:
                os.unlink("screen.jpg")
            except:
                logger.warning("could not unlink temporary screenshot")
            if template_image:
                pass
            else:
                try:
                    os.unlink("cf_template.png")
                except:  # noqa
                    logger.warning("could not unlink template file cf_template.png")

    async def bypass_insecure_connection_warning(self):
        """
        when you enter a site where the certificate is invalid
        you get a warning. call this function to "proceed"
        :return:
        :rtype:
        """
        body = await self.select("body")
        await body.send_keys("thisisunsafe")

    async def mouse_move(self, x: float, y: float, steps=10, flash=False):
        steps = 1 if (not steps or steps < 1) else steps
        # probably the worst waay of calculating this. but couldn't think of a better solution today.
        if steps > 1:
            step_size_x = x // steps
            step_size_y = y // steps
            pathway = [(step_size_x * i, step_size_y * i) for i in range(steps + 1)]
            for point in pathway:
                if flash:
                    await self.flash_point(point[0], point[1])
                await self.send(
                    cdp.input_.dispatch_mouse_event(
                        "mouseMoved", x=point[0], y=point[1]
                    )
                )
        else:
            await self.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y))
        if flash:
            await self.flash_point(x, y)
        else:
            await self.sleep(0.05)
        await self.send(cdp.input_.dispatch_mouse_event("mouseReleased", x=x, y=y))
        if flash:
            await self.flash_point(x, y)

    async def scroll_bottom_reached(self):
        """
        returns True if scroll is at the bottom of the page
        handy when you need to scroll over paginated pages of different lengths
        :return:
        :rtype:
        """

        res = await self.evaluate(
            "document.body.offsetHeight - window.innerHeight == window.scrollY"
        )
        if res:
            return res[0].value

    async def mouse_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        buttons: typing.Optional[int] = 1,
        modifiers: typing.Optional[int] = 0,
        _until_event: typing.Optional[type] = None,
    ):
        """native click on position x,y
        :param y:
        :type y:
        :param x:
        :type x:
        :param button: str (default = "left")
        :param buttons: which button (default 1 = left)
        :param modifiers: *(Optional)* Bit field representing pressed modifier keys.
                Alt=1, Ctrl=2, Meta/Command=4, Shift=8 (default: 0).
        :param _until_event: internal. event to wait for before returning
        :return:
        """

        await self.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=x,
                y=y,
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )

        await self.send(
            cdp.input_.dispatch_mouse_event(
                "mouseReleased",
                x=x,
                y=y,
                modifiers=modifiers,
                button=cdp.input_.MouseButton(button),
                buttons=buttons,
                click_count=1,
            )
        )

    async def mouse_drag(
        self,
        source_point: tuple[float, float],
        dest_point: tuple[float, float],
        relative: bool = False,
        steps: int = 1,
    ):
        """
        drag mouse from one point to another. holding button pressed
        you are probably looking for :py:meth:`element.Element.mouse_drag` method. where you
        can drag on the element

        :param dest_point:
        :type dest_point:
        :param source_point:
        :type source_point:
        :param relative: when True, treats point as relative. for example (-100, 200) will move left 100px and down 200px
        :type relative:

        :param steps: move in <steps> points, this could make it look more "natural" (default 1),
               but also a lot slower.
               for very smooth action use 50-100
        :type steps: int
        :return:
        :rtype:
        """
        if relative:
            dest_point = (
                source_point[0] + dest_point[0],
                source_point[1] + dest_point[1],
            )
        await self.send(
            cdp.input_.dispatch_mouse_event(
                "mousePressed",
                x=source_point[0],
                y=source_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )
        steps = 1 if (not steps or steps < 1) else steps

        if steps == 1:
            await self.send(
                cdp.input_.dispatch_mouse_event(
                    "mouseMoved", x=dest_point[0], y=dest_point[1]
                )
            )
        elif steps > 1:
            # probably the worst waay of calculating this. but couldn't think of a better solution today.
            step_size_x = (dest_point[0] - source_point[0]) / steps
            step_size_y = (dest_point[1] - source_point[1]) / steps
            pathway = [
                (source_point[0] + step_size_x * i, source_point[1] + step_size_y * i)
                for i in range(steps + 1)
            ]
            for point in pathway:
                await self.send(
                    cdp.input_.dispatch_mouse_event(
                        "mouseMoved",
                        x=point[0],
                        y=point[1],
                    )
                )
                await asyncio.sleep(0)

        await self.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=dest_point[0],
                y=dest_point[1],
                button=cdp.input_.MouseButton("left"),
            )
        )

    async def flash_point(self, x, y, duration=0.5, size=10):
        style = (
            "position:absolute;z-index:99999999;padding:0;margin:0;"
            "left:{:.1f}px; top: {:.1f}px;"
            "opacity:1;"
            "width:{:d}px;height:{:d}px;border-radius:50%;background:red;"
            "animation:show-pointer-ani {:.2f}s ease 1;"
        ).format(x - 8, y - 8, size, size, duration)
        script = (
            """
                var css = document.styleSheets[0];
                for( let css of [...document.styleSheets]) {{
                    try {{
                        css.insertRule(`
                        @keyframes show-pointer-ani {{
                              0% {{ opacity: 1; transform: scale(1, 1);}}
                              50% {{ transform: scale(3, 3);}}
                              100% {{ transform: scale(1, 1); opacity: 0;}}
                        }}`,css.cssRules.length);
                        break;
                    }} catch (e) {{
                        console.log(e)
                    }}
                }};
                var _d = document.createElement('div');
                _d.style = `{0:s}`;
                _d.id = `{1:s}`;
                document.body.insertAdjacentElement('afterBegin', _d);
    
                setTimeout( () => document.getElementById('{1:s}').remove(), {2:d});
    
            """.format(
                style, secrets.token_hex(8), int(duration * 1000)
            )
            .replace("  ", "")
            .replace("\n", "")
        )
        await self.send(
            cdp.runtime.evaluate(
                script,
                await_promise=True,
                user_gesture=True,
            )
        )

    def __eq__(self, other: Tab):
        try:
            return other.target == self.target
        except (AttributeError, TypeError):
            return False

    def __getattr__(self, item):
        try:
            return getattr(self._target, item)
        except AttributeError:
            raise AttributeError(
                f'"{self.__class__.__name__}" has no attribute "%s"' % item
            )

    def __repr__(self):
        extra = ""
        if self.target.url:
            extra = f"[url: {self.target.url}]"
        s = f"<{type(self).__name__} [{self.target_id}] [{self.type_}] {extra}>"
        return s


#
# from .connection import Transaction
#
#
# class TargetTransaction(Transaction):
#     session_id: cdp.target.SessionID
#
#     def __init__(self, cdp_obj: Generator, session_id: cdp.target.SessionID):
#         """
#         :param cdp_obj:
#         """
#         self.session_id = session_id
#         super().__init__(cdp_obj=cdp_obj)
#
#     @property
#     def message(self):
#         return json.dumps(
#             {
#                 "method": self.method,
#                 "params": self.params,
#                 "id": self.id,
#                 "sessionId": self.session_id,
#             }
#         )
#
#
# class TargetSession:
#
#     def __init__(self, tab: Tab):
#         self._tab = tab
#         self._browser = tab.browser
#         self._session_id = None
#         self._target_id = None
#
#     async def create_session(
#             self, target: Union[cdp.target.TargetID, cdp.target.TargetInfo]
#     ):
#         if isinstance(target, cdp.target.TargetID):
#             target = await self._tab.send(cdp.target.get_target_info(target))
#
#         self._target_id: cdp.target.TargetID = await self._tab.send(
#             cdp.target.create_target(url="")
#         )
#         self._session_id: cdp.target.SessionID = await self._tab.send(
#             cdp.target.attach_to_target(self._target_id, flatten=True)
#         )
#
#     async def send(self, cdp_obj: Generator[dict[str, Any], dict[str, Any], Any]):
#         tx = TargetTransaction(cdp_obj, self._session_id)
#         tx.id = next(self._tab.__count__)
#         self._tab.mapper.update({tx.id: tx})
#         return await self._tab.send(
#             cdp.target.send_message_to_target(
#                 json.dumps(tx.message), self._session_id, target_id=self._target_id
#             )
#         )
#
# #
# # class Frame(cdp.page.Frame):
# #     execution_contexts: typing.Dict[str, ExecutionContext] = {}
# #
# #     def __init__(self, id_: cdp.page.FrameId, **kw):
# #         none_gen = itertools.repeat(None)
# #         param_names = util.get_all_param_names(self.__class__)
# #         param_names.remove("execution_contexts")
# #         for k in kw:
# #             param_names.remove(k)
# #         params = dict(zip(param_names, none_gen))
# #         params.update({"id_": id_, **kw})
# #         super().__init__(**params)
#
# #
# # class ExecutionContext(dict):
# #     id: cdp.runtime.ExecutionContextId
# #     frame_id: str
# #     unique_id: str
# #     _tab: Tab
# #
# #     def __init__(self, *a, **kw):
# #         super().__init__()
# #         super().__setattr__("__dict__", self)
# #         d: typing.Dict[str, Union[Tab, str]] = dict(*a, **kw)
# #         self._tab: Tab = d.pop("tab", None)
# #         self.__dict__.update(d)
# #
# #     def __repr__(self):
# #         return "<ExecutionContext (\n{}\n)".format(
# #             "".join(f"\t{k} = {v}\n" for k, v in super().items() if k not in ("_tab"))
# #         )
# #
# #     async def evaluate(
# #             self,
# #             expression,
# #             allow_unsafe_eval_blocked_by_csp: bool = True,
# #             await_promises: bool = False,
# #             generate_preview: bool = False,
# #     ):
# #         try:
# #             raw = await self._tab.send(
# #                 cdp.runtime.evaluate(
# #                     expression=expression,
# #                     context_id=self.get("id_"),
# #                     generate_preview=generate_preview,
# #                     return_by_value=False,
# #                     allow_unsafe_eval_blocked_by_csp=allow_unsafe_eval_blocked_by_csp,
# #                     await_promise=await_promises,
# #                 )
# #             )
# #             if raw:
# #                 remote_object, errors = raw
# #                 if errors:
# #                     raise ProtocolException(errors)
# #
# #                 if remote_object:
# #                     return remote_object
# #
# #                 # else:
# #                 #     return remote_object, errors
# #
# #         except:  # noqa
# #             raise
